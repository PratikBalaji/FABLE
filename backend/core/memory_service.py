"""
Cross-session semantic memory backed by Supabase + pgvector.

Stores each chat turn and each adversarial transcript with a 384-d embedding
(reusing knowledge_engine's MiniLM model), then retrieves semantically related
memories for a new prompt — scoped to the user via match_memory_chunks().

All writes are best-effort: a memory failure logs a warning but never breaks a run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from .config import settings
from .db import get_db, match_memory_chunks, vector_literal
from .knowledge_engine import knowledge_engine
from .pii import abstract_for_memory

log = structlog.get_logger()


class MemoryService:
    # --- embedding -------------------------------------------------------
    def _embed(self, text: str) -> list[float]:
        return knowledge_engine.embed_text(text)

    def _store_chunk(
        self,
        user_id: str,
        source_type: str,
        source_id: str | None,
        session_id: str | None,
        domain: str | None,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        identity_id: str | None = None,
    ) -> None:
        db = get_db()
        meta = dict(metadata or {})
        meta["embedding_model"] = settings.embedding_model  # drift detection
        db.table("memory_chunks").insert(
            {
                "user_id": user_id,
                # F-006: populate identity_id so the RLS identity backstop applies.
                # In multi-user mode user_id already carries the identity id.
                "identity_id": identity_id or user_id,
                "source_type": source_type,
                "source_id": source_id,
                "session_id": session_id,
                "domain": domain,
                "content": content[:4000],
                "embedding": vector_literal(embedding),
                "metadata": meta,
            }
        ).execute()

    # --- writes ----------------------------------------------------------
    async def store_chat_turn(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        model_used: str | None = None,
        scores: dict[str, float] | None = None,
        adversarial_run_id: str | None = None,
        router=None,
    ) -> str | None:
        try:
            db = get_db()
            # F-010: abstract before embedding — satisfies "no raw PII in memory_chunks" invariant.
            # chat_messages keeps original redacted text for display; memory_chunks gets abstracted.
            abstract_content = await abstract_for_memory(content, scores, router)
            emb = self._embed(abstract_content)
            res = (
                db.table("chat_messages")
                .insert(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "identity_id": user_id,  # F-006: identity backstop
                        "role": role,
                        "content": content,
                        "model_used": model_used,
                        "scores": scores,
                        "adversarial_run_id": adversarial_run_id,
                        "embedding": vector_literal(emb),
                    }
                )
                .execute()
            )
            msg_id = res.data[0]["id"] if res.data else None
            self._store_chunk(
                user_id, "chat_turn", msg_id, session_id, None, abstract_content,
                emb, {"role": role, "model": model_used}, identity_id=user_id,
            )
            db.table("chat_sessions").update(
                {"updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", session_id).execute()
            return msg_id
        except Exception as exc:  # noqa: BLE001
            log.warning("store_chat_turn_failed", error=str(exc))
            return None

    async def store_adversarial_run(
        self,
        *,
        user_id: str,
        session_id: str | None,
        task_id: str,
        domain: str,
        input_text: str,
        final_output: str,
        adversarial_meta: dict[str, Any],
        scores: dict[str, float] | None,
        pipeline: list[str] | None,
        model_used: str | None,
        messages: list[dict[str, Any]],
        router=None,
    ) -> str | None:
        try:
            db = get_db()
            res = (
                db.table("adversarial_runs")
                .insert(
                    {
                        "user_id": user_id,
                        "identity_id": user_id,  # F-006: identity backstop
                        "session_id": session_id,
                        "task_id": task_id,
                        "domain": domain,
                        "input_text": input_text,
                        "final_output": final_output,
                        "rounds_completed": adversarial_meta.get("rounds_completed", 0),
                        "max_rounds": adversarial_meta.get("max_rounds", 0),
                        "judge_verdict": adversarial_meta.get("judge_verdict"),
                        "judge_score": adversarial_meta.get("judge_score"),
                        "judge_rationale": adversarial_meta.get("judge_rationale"),
                        "unresolved_issues": adversarial_meta.get("unresolved_issues"),
                        "scores": scores,
                        "pipeline": pipeline,
                        "model_used": model_used,
                    }
                )
                .execute()
            )
            run_id = res.data[0]["id"] if res.data else None

            rows = []
            for seq, m in enumerate(messages):
                md = m.get("metadata") or {}
                rows.append(
                    {
                        "run_id": run_id,
                        "user_id": user_id,
                        "identity_id": user_id,  # F-006: identity backstop
                        "round": md.get("round", 0),
                        "seq": seq,
                        "role": m.get("role"),
                        "content": m.get("content") or "",
                        "model": md.get("model"),
                        "usage": md.get("usage"),
                    }
                )
            if rows:
                db.table("adversarial_messages").insert(rows).execute()

            if final_output:
                # F-010: abstract combined transcript before embedding
                raw_for_abstract = f"{input_text}\n\n{final_output}"
                abstract_content = await abstract_for_memory(raw_for_abstract, scores, router)
                emb = self._embed(abstract_content)
                self._store_chunk(
                    user_id, "adversarial_final", run_id, session_id, domain,
                    abstract_content, emb,
                    {"task_id": task_id, "verdict": adversarial_meta.get("judge_verdict")},
                    identity_id=user_id,
                )
            return run_id
        except Exception as exc:  # noqa: BLE001
            log.warning("store_adversarial_run_failed", error=str(exc))
            return None

    # --- reads -----------------------------------------------------------
    async def retrieve(
        self, user_id: str, query: str, top_k: int = 8, threshold: float = 0.15
    ) -> list[dict[str, Any]]:
        try:
            emb = self._embed(query)
            hits = match_memory_chunks(user_id, emb, top_k)
            return [h for h in hits if (h.get("similarity") or 0.0) >= threshold]
        except Exception as exc:  # noqa: BLE001
            log.warning("memory_retrieve_failed", error=str(exc))
            return []

    async def grouped_context(self, user_id: str, query: str, top_k: int = 6) -> str:
        """Return related past memories formatted as the retrieved_context block agents consume."""
        hits = await self.retrieve(user_id, query, top_k=top_k)
        if not hits:
            return ""
        lines: list[str] = []
        for i, h in enumerate(hits, 1):
            src = h.get("source_type", "memory")
            dom = h.get("domain") or "general"
            sim = h.get("similarity") or 0.0
            lines.append(f"[Memory {i} — {src}, {dom}, relevance: {sim:.2f}]")
            lines.append((h.get("content") or "")[:300])
        return "\n\n".join(lines)


memory_service = MemoryService()
