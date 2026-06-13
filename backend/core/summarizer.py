"""LLM summarizer — per-agent and run-level summaries via asyncio.gather."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router.model_router import ModelRouter

from .config import settings

_AGENT_SYS = (
    "You are a concise technical analyst. "
    "Summarize the agent output below in 1–2 clear sentences. "
    "Be direct. No preamble, no markdown."
)

_RUN_SYS = (
    "You are a concise technical analyst. "
    "Summarize the key outcome of this multi-agent AI collaboration in 2–3 sentences. "
    "Focus on what was determined and the confidence level. No preamble."
)


async def summarize_run(
    input_text: str,
    messages: list[dict],
    final_output: str,
    *,
    router: "ModelRouter",
) -> dict:
    """
    Generate per-agent summaries + a run-level summary concurrently.

    Returns::
        {
            "run_summary": str,
            "per_agent": {message_id: summary, ...},
        }

    Never raises — failures produce empty strings so the run response is unaffected.

    Flags (config):
      - summaries_enabled=False  → returns empty immediately (0 LLM calls)
      - summaries_per_agent=False → run-level summary only (1 LLM call, no per-agent)
    """
    if not settings.summaries_enabled:
        return {"run_summary": "", "per_agent": {}}

    async def _agent_summary(msg: dict) -> tuple[str, str]:
        try:
            resp = await router.complete(
                system=_AGENT_SYS,
                user=f"[{msg['role'].upper()} OUTPUT]\n\n{msg['content'][:2000]}",
                force_model=settings.secondary_model,
            )
            return msg["message_id"], resp.content.strip()
        except Exception:
            return msg["message_id"], ""

    async def _run_summary() -> str:
        try:
            transcript = "\n\n".join(
                f"[{m['role'].upper()}]: {m['content'][:600]}"
                for m in messages
            )
            resp = await router.complete(
                system=_RUN_SYS,
                user=(
                    f"Task:\n{input_text[:500]}\n\n"
                    f"Agent Transcript:\n{transcript[:3000]}\n\n"
                    f"Final Output:\n{final_output[:1000]}"
                ),
                force_model=settings.secondary_model,
            )
            return resp.content.strip()
        except Exception:
            return ""

    # Run-level-only path (default): single LLM call, no per-agent fan-out.
    if not settings.summaries_per_agent:
        run_summary = await _run_summary()
        return {"run_summary": run_summary, "per_agent": {}}

    # Full path: per-agent + run-level, concurrent.
    results = await asyncio.gather(
        *[_agent_summary(m) for m in messages],
        _run_summary(),
        return_exceptions=True,
    )

    per_agent: dict[str, str] = {}
    for i, result in enumerate(results[: len(messages)]):
        if isinstance(result, BaseException):
            per_agent[messages[i]["message_id"]] = ""
        else:
            mid, summary = result  # type: ignore[misc]
            per_agent[mid] = summary

    last = results[-1]
    run_summary: str = last if isinstance(last, str) else ""

    return {"run_summary": run_summary, "per_agent": per_agent}
