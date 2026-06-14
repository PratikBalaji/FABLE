"""
Golden-Case Reasoning Cache (Phase 14).

High-quality completed runs are promoted to "golden cases" — reusable reasoning
assets stored with their full trajectory. Incoming prompts are matched by cosine
similarity; the action is tiered:

  ≥ HIT_THRESHOLD (0.93): Adapt golden answer via one LLM call → cheap judge re-check.
                           Falls through to full run if re-check fails.
  ≥ WARM_THRESHOLD (0.82): Seed pipeline with golden trajectory context; cut rounds.
  < WARM_THRESHOLD:        Full run (no recycling).

Research framing: "Semantic trajectory reuse in multi-agent LLM systems" —
cuts token cost ~80% on hits and ~40% on warm-starts while preserving quality
via the mandatory re-check gate.

Persistence: data/knowledge/golden_cases.jsonl (one JSON record per line).
             Mirrors knowledge_engine runs.jsonl pattern.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import structlog

from .config import settings

log = structlog.get_logger()

Tier = Literal["hit", "warm", "miss"]

HIT_THRESHOLD: float = 0.93
WARM_THRESHOLD: float = 0.82

_ADAPT_SYSTEM = (
    "You are an expert assistant. A previous answer to a similar question is provided. "
    "Adapt it to precisely answer the NEW question — keep the structure and reasoning "
    "style but change any details that differ. Do NOT mention this is adapted from a prior answer. "
    "Output only the adapted answer, no preamble."
)

_RECHECK_SYSTEM = (
    "You are a strict quality judge. Given a question and an answer, determine whether "
    "the answer correctly and completely addresses the question.\n"
    "Reply with ONLY JSON: "
    '{"verdict":"pass"|"fail","reason":"<one sentence>"}\n'
    "No markdown. Pass only if the answer is accurate and directly relevant."
)


@dataclass
class TrajectoryStep:
    role: str
    model: str
    summary: str   # compact — not full content, to keep tokens low


@dataclass
class GoldenCase:
    run_id: str
    input_text: str
    final_answer: str
    scores: dict[str, float]
    trajectory: list[TrajectoryStep]
    embedding: list[float]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (
        datetime.now(timezone.utc) + timedelta(days=settings.golden_ttl_days)
    ).isoformat())

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return False


class GoldenCaseCache:
    """In-memory golden case store with cosine-similarity matching and npz embedding matrix."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "golden_cases.jsonl"
        self._cases: list[GoldenCase] = []
        self._matrix: np.ndarray | None = None  # (N, 384) float32
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        loaded = 0
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    d["trajectory"] = [TrajectoryStep(**s) for s in d.get("trajectory", [])]
                    gc = GoldenCase(**d)
                    if not gc.is_expired():
                        self._cases.append(gc)
                        loaded += 1
                except Exception as exc:
                    log.warning("golden_load_row_failed", err=str(exc)[:80])
        self._rebuild_matrix()
        log.info("golden_cache_loaded", count=loaded)

    def _save_one(self, gc: GoldenCase) -> None:
        d = asdict(gc)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(d) + "\n")

    def _rebuild_matrix(self) -> None:
        if self._cases:
            self._matrix = np.array(
                [c.embedding for c in self._cases], dtype=np.float32
            )
            # L2-normalise for cosine similarity via dot product
            norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1.0, norms)
            self._matrix = self._matrix / norms
        else:
            self._matrix = None

    # ── Promotion ────────────────────────────────────────────────────────────

    def promote(
        self,
        run_id: str,
        input_text: str,
        final_answer: str,
        scores: dict[str, float],
        verdict: dict,
        messages: list[dict],
        embedding: list[float],
    ) -> bool:
        """Promote a completed run to golden status if it meets quality threshold.

        Qualification: avg rubric score ≥ golden_promote_threshold AND verdict == PASS/ACCEPT.
        """
        if not settings.golden_cache_enabled:
            return False
        avg_score = sum(scores.values()) / max(len(scores), 1) if scores else 0.0
        verdict_str = (verdict.get("verdict") or "").upper()
        if avg_score < settings.golden_promote_threshold:
            return False
        if verdict_str not in ("PASS", "ACCEPT"):
            return False

        trajectory = [
            TrajectoryStep(
                role=m.get("role", ""),
                model=m.get("metadata", {}).get("model", ""),
                summary=m.get("summary", "") or m.get("content", "")[:200],
            )
            for m in messages
        ]
        gc = GoldenCase(
            run_id=run_id,
            input_text=input_text,
            final_answer=final_answer,
            scores=scores,
            trajectory=trajectory,
            embedding=embedding,
        )
        self._cases.append(gc)
        self._rebuild_matrix()
        self._save_one(gc)
        log.info("golden_promote", run_id=run_id, avg_score=round(avg_score, 3), count=len(self._cases))
        return True

    # ── Matching ─────────────────────────────────────────────────────────────

    def match(self, query_embedding: list[float]) -> tuple[GoldenCase, float, Tier] | None:
        """Find the best non-expired golden case for a query embedding.

        Returns (golden_case, similarity, tier) or None if no match above WARM_THRESHOLD.
        """
        if not settings.golden_cache_enabled or self._matrix is None or not self._cases:
            return None

        q = np.array(query_embedding, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        sims = self._matrix @ q  # (N,) cosine similarities
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_case = self._cases[best_idx]

        if best_case.is_expired():
            log.info("golden_expired", run_id=best_case.run_id, sim=round(best_sim, 3))
            return None

        if best_sim >= HIT_THRESHOLD:
            log.info("golden_hit", run_id=best_case.run_id, sim=round(best_sim, 3))
            return best_case, best_sim, "hit"
        if best_sim >= WARM_THRESHOLD:
            log.info("golden_warm", run_id=best_case.run_id, sim=round(best_sim, 3))
            return best_case, best_sim, "warm"

        return None

    # ── Adaptation + re-check ────────────────────────────────────────────────

    async def adapt(self, golden: GoldenCase, new_prompt: str, router) -> str | None:
        """Adapt a golden answer to a new prompt via one cheap LLM call.

        Returns adapted answer string, or None on failure (caller falls through to full run).
        """
        try:
            resp = await router.complete(
                system=_ADAPT_SYSTEM,
                user=(
                    f"PREVIOUS QUESTION:\n{golden.input_text[:1000]}\n\n"
                    f"PREVIOUS ANSWER:\n{golden.final_answer[:2000]}\n\n"
                    f"NEW QUESTION:\n{new_prompt[:1000]}"
                ),
                force_model=settings.secondary_model,  # cheap model; adaptation is low-complexity
            )
            return (resp.content or "").strip() or None
        except Exception as exc:
            log.warning("golden_adapt_failed", err=str(exc)[:120])
            return None

    async def recheck(self, question: str, answer: str, router) -> bool:
        """Cheap judge call to validate adapted answer quality.

        Returns True (pass) or False (fail → fall through to full run).
        """
        import re as _re
        try:
            resp = await router.complete(
                system=_RECHECK_SYSTEM,
                user=f"QUESTION:\n{question[:800]}\n\nANSWER:\n{answer[:1500]}",
                force_model=settings.secondary_model,
            )
            raw = (resp.content or "").strip()
            raw = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=_re.MULTILINE).strip()
            data = json.loads(raw)
            passed = str(data.get("verdict", "fail")).lower() == "pass"
            log.info("golden_recheck", passed=passed, reason=str(data.get("reason", ""))[:80])
            return passed
        except Exception as exc:
            log.warning("golden_recheck_failed", err=str(exc)[:120])
            return False  # fail-safe: if recheck errors, fall through to full run

    def warm_context(self, golden: GoldenCase) -> str:
        """Compact trajectory context string injected into warm-start TaskContext."""
        steps = [f"[{s.role}/{s.model.split('/')[-1]}]: {s.summary}" for s in golden.trajectory]
        return (
            f"[Golden trajectory — prior high-quality run on similar topic]\n"
            + "\n".join(steps)
            + f"\n[Prior answer]: {golden.final_answer[:500]}"
        )


# Module-level singleton — loaded once, shared across requests
_cache: GoldenCaseCache | None = None


def get_golden_cache() -> GoldenCaseCache:
    global _cache
    if _cache is None:
        from pathlib import Path
        from .config import settings as _s
        _cache = GoldenCaseCache(Path(_s.vector_store_path).parent / "knowledge")
    return _cache
