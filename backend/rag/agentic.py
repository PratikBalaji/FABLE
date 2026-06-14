"""
Agentic RAG — Corrective RAG (CRAG-lite), Phase 18.

Pipeline:
  1. Retrieve candidates from the FAISS corpus (+ pgvector memory in multi-user mode).
  2. Grade each candidate relevant/irrelevant to the query via ONE cheap LLM call.
  3. If too few survive AND hops remain, rewrite the query (LLM) and re-retrieve.
  4. Return a graded, prompt-ready context block (UNTRUSTED framing applied upstream).

Every step is best-effort: any failure returns "" / keeps candidates, so a run never
breaks because retrieval hiccuped. Bounded by agentic_rag_max_hops (default 2).
"""
from __future__ import annotations

import json
import re

import structlog

from ..core.config import settings

log = structlog.get_logger()

_GRADE_SYSTEM = (
    "You are a retrieval relevance grader. Given a user QUERY and a numbered list of "
    "CANDIDATE passages, decide which passages contain information useful for answering "
    "the query. Reply with ONLY raw JSON, no markdown:\n"
    '{"relevant":[<1-based indices of useful passages>]}\n'
    "Be strict: include a passage only if it materially helps answer the query. "
    "If none are useful, return {\"relevant\":[]}."
)

_REWRITE_SYSTEM = (
    "You rewrite a search query to retrieve better documents. The previous query returned "
    "weak results. Produce ONE improved search query — broader or rephrased with key "
    "entities/synonyms. Output ONLY the rewritten query text, no quotes, no preamble."
)


async def _grade(query: str, candidates: list[dict], router) -> list[dict]:
    """Keep only candidates the grader marks relevant. Fail-safe: keep all on error."""
    if not candidates or router is None:
        return candidates
    listing = "\n".join(f"[{i}] {c['text'][:500]}" for i, c in enumerate(candidates, 1))
    try:
        resp = await router.complete(
            system=_GRADE_SYSTEM,
            user=f"QUERY:\n{query[:800]}\n\nCANDIDATES:\n{listing}",
            role_hint="rag_grade",
            force_model=settings.secondary_model,
        )
        raw = (resp.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        idxs = json.loads(raw).get("relevant", [])
        keep = [candidates[i - 1] for i in idxs if isinstance(i, int) and 1 <= i <= len(candidates)]
        return keep if keep else []
    except Exception as exc:  # noqa: BLE001
        log.warning("agentic_grade_failed", err=str(exc)[:120])
        return candidates  # fail-safe: don't drop everything on a grader error


async def _rewrite(query: str, router) -> str | None:
    if router is None:
        return None
    try:
        resp = await router.complete(
            system=_REWRITE_SYSTEM,
            user=f"PREVIOUS QUERY:\n{query[:500]}",
            role_hint="rag_rewrite",
            force_model=settings.secondary_model,
        )
        rewritten = (resp.content or "").strip()
        return rewritten or None
    except Exception as exc:  # noqa: BLE001
        log.warning("agentic_rewrite_failed", err=str(exc)[:120])
        return None


def _format(candidates: list[dict]) -> str:
    if not candidates:
        return ""
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(f"[{i}] (source: {c['source']})\n{c['text']}")
    return "\n\n".join(lines)


async def agentic_retrieve(
    query: str,
    router,
    *,
    identity_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """CRAG-lite retrieval. Returns a graded context block, or "" if nothing relevant.
    Never raises — callers treat "" as 'no RAG context' and proceed."""
    if not settings.agentic_rag_enabled:
        return ""

    max_hops = max(1, settings.agentic_rag_max_hops)
    min_relevant = settings.agentic_rag_min_relevant
    current_query = query
    relevant: list[dict] = []

    try:
        for hop in range(max_hops):
            candidates = await _retrieve_all(current_query, identity_id, user_id)
            relevant = await _grade(current_query, candidates, router)
            log.info(
                "agentic_rag_hop",
                hop=hop + 1,
                candidates=len(candidates),
                relevant=len(relevant),
                query_preview=current_query[:60],
            )
            if len(relevant) >= min_relevant or hop == max_hops - 1:
                break
            # Weak result → rewrite query and try again
            rewritten = await _rewrite(current_query, router)
            if not rewritten or rewritten == current_query:
                break
            current_query = rewritten
    except Exception as exc:  # noqa: BLE001
        log.warning("agentic_retrieve_failed", err=str(exc)[:120])
        return ""

    return _format(relevant)


async def _retrieve_all(query: str, identity_id: str | None, user_id: str | None) -> list[dict]:
    """Pool FAISS corpus + (multi-user) pgvector memory candidates."""
    k = settings.agentic_rag_top_k
    pooled: list[dict] = []

    try:
        from .pipeline import vector_store
        for hit in vector_store.retrieve(query, top_k=k, identity_id=identity_id):
            pooled.append({
                "text": hit.get("chunk", ""),
                "source": (hit.get("metadata") or {}).get("source", "corpus"),
                "score": hit.get("score", 0.0),
            })
    except Exception as exc:  # noqa: BLE001
        log.warning("agentic_faiss_retrieve_failed", err=str(exc)[:120])

    if settings.use_supabase and user_id:
        try:
            from ..core.memory_service import memory_service
            for h in await memory_service.retrieve(user_id, query, top_k=k):
                pooled.append({
                    "text": (h.get("content") or "")[:1000],
                    "source": h.get("source_type", "memory"),
                    "score": h.get("similarity", 0.0),
                })
        except Exception as exc:  # noqa: BLE001
            log.warning("agentic_memory_retrieve_failed", err=str(exc)[:120])

    return pooled
