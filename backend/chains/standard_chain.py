"""
Phase 19 — LangChain (LCEL) orchestrator for the standard pipeline.

Standard mode is a linear role sequence (default: analyst → critic → synthesizer),
which is a textbook LCEL composition. To keep the agent logic as the single source of
truth (and guarantee score parity with the native path), each role is wrapped as a
`RunnableLambda` that dispatches the *already-registered* AgentBus handler, and the
roles are composed with the LCEL `|` operator into a `RunnableSequence`.

This gives a genuine LangChain runtime (`RunnableSequence.ainvoke`, auto-traced by
LangSmith) without reimplementing any prompt — so the LangChain-vs-LangGraph comparison
isolates the orchestration layer, not the prompts.

If langchain-core is not installed, importing `run_pipeline_langchain` raises
ImportError and the caller falls back to the native bus.stream_collaboration loop.
"""
from __future__ import annotations

import structlog

from ..core.bus import AgentMessage, TaskContext, bus

log = structlog.get_logger()

# Optional dep — ImportError here propagates so the caller can fall back to asyncio.
from langchain_core.runnables import RunnableLambda  # noqa: E402


def _role_step(role: str) -> "RunnableLambda":
    """Wrap one agent role as an LCEL Runnable. Dispatches the registered handler,
    which appends its message to ctx.history, then passes ctx down the chain."""

    async def _step(ctx: TaskContext) -> TaskContext:
        await bus.dispatch(role, ctx)
        return ctx

    return RunnableLambda(_step).with_config(run_name=f"agent:{role}")


def _build_chain(pipeline: list[str]):
    chain = _role_step(pipeline[0])
    for role in pipeline[1:]:
        chain = chain | _role_step(role)
    return chain


async def run_pipeline_langchain(
    task_ctx: TaskContext, pipeline: list[str]
) -> list[AgentMessage]:
    """Run the standard pipeline as an LCEL RunnableSequence.

    Returns the messages produced this run. task_ctx.history is empty at entry for
    standard mode (no planner), so every appended message belongs to this pipeline.
    """
    before = len(task_ctx.history)
    chain = _build_chain(pipeline)
    log.info("standard_langchain_start", pipeline=pipeline)
    await chain.ainvoke(task_ctx)
    return list(task_ctx.history[before:])
