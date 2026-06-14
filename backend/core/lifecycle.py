"""
Lifecycle orchestrator — wires the agent bus, knowledge engine, and learned
model router into a full run that accumulates knowledge over time.
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator

from .bus import AgentMessage, TaskContext, bus
from .config import settings
from .concurrency import ConcurrencyLimitExceeded, identity_slot
from .embeddings import embed_text
from .golden_cache import get_golden_cache
from .guardrails import GuardrailBlocked, guardrail_engine
from .knowledge_engine import knowledge_engine
from .summarizer import summarize_run
from ..evaluation.rubric import score as rubric_score
from ..evaluation.verdict import derive_verdict
from ..router.model_router import ModelRouter, router as default_router


async def run_task(
    input_text: str,
    domain: str,
    pipeline: list[str] | None = None,
    *,
    user_id: str | None = None,
    router: ModelRouter | None = None,
) -> dict:
    """
    Execute a full multi-agent collaboration run with knowledge accumulation.

    1. Query the knowledge engine for relevant context from past runs
    2. Ask the engine which model historically performs best for this query
    3. Run the agent pipeline with learned routing
    4. Score the output
    5. Feed everything back into the knowledge engine
    6. Return messages + updated graph state
    """
    result: dict = {}
    async for event in _run_core(input_text, domain, pipeline, user_id=user_id, router=router):
        if event["type"] == "complete":
            result = event["data"]
        elif event["type"] == "error":
            raise event["exc"]
    return result


async def run_task_streaming(
    input_text: str,
    domain: str,
    pipeline: list[str] | None = None,
    *,
    user_id: str | None = None,
    router: ModelRouter | None = None,
) -> AsyncGenerator[dict, None]:
    """Yield events as the pipeline executes (SSE streaming).

    Event types:
      {"type": "agent_message", "data": {role, content, metadata, timestamp, message_id}}
      {"type": "complete",      "data": {task_id, domain, pipeline, scores, model_used,
                                          knowledge_graph, run_summary, final_answer, verdict}}
      {"type": "error",         "data": {"detail": str}}
    """
    return _run_core(input_text, domain, pipeline, user_id=user_id, router=router)


async def _run_core(
    input_text: str,
    domain: str,
    pipeline: list[str] | None,
    *,
    user_id: str | None,
    router: ModelRouter | None,
):
    """Shared generator — yields events for both blocking and streaming callers."""
    _router = router or default_router

    if pipeline is None:
        pipeline = ["analyst", "critic", "synthesizer"]

    task_id = str(uuid.uuid4())

    # F-035: per-identity concurrency guard
    try:
        async with identity_slot(user_id):
            async for event in _run_core_inner(
                input_text, domain, pipeline, task_id, user_id=user_id, router=_router
            ):
                yield event
    except ConcurrencyLimitExceeded as exc:
        yield {"type": "error", "exc": exc, "data": {"detail": str(exc)}}
    return


async def _run_core_inner(
    input_text: str,
    domain: str,
    pipeline: list[str],
    task_id: str,
    *,
    user_id: str | None,
    router: ModelRouter | None,
):
    """Inner generator (concurrency slot already held)."""
    _router = router or default_router

    # Step -1: Golden-case cache check (before guardrail — fast, no LLM calls on miss)
    golden_cache = get_golden_cache()
    try:
        query_emb = embed_text(input_text)
        match = golden_cache.match(query_emb)
    except Exception:
        match = None

    if match is not None:
        golden, sim, tier = match

        if tier == "hit":
            # Adapt the golden answer to this specific prompt
            adapted = await golden_cache.adapt(golden, input_text, _router)
            if adapted:
                passed = await golden_cache.recheck(input_text, adapted, _router)
                if passed:
                    # Yield a recycled complete event — ~2 LLM calls instead of full pipeline
                    recycled_verdict = derive_verdict(golden.scores)
                    graph_state = knowledge_engine.get_graph_state()
                    yield {
                        "type": "complete",
                        "data": {
                            "task_id": task_id,
                            "domain": domain,
                            "pipeline": pipeline,
                            "messages": [],
                            "scores": golden.scores,
                            "model_used": "golden_cache",
                            "knowledge_graph": graph_state,
                            "run_summary": f"[Recycled from golden case {golden.run_id[:8]}]",
                            "final_answer": adapted,
                            "verdict": recycled_verdict,
                            "metadata": {
                                "recycled": True,
                                "golden_run_id": golden.run_id,
                                "similarity": round(sim, 4),
                            },
                        },
                    }
                    return
            # Recheck failed or adapt failed — fall through to full run
        elif tier == "warm":
            # Inject golden trajectory as seed context; reduce adversarial rounds
            # (passed via metadata to lifecycle; bus + agents see it as prior context)
            warm_ctx = golden_cache.warm_context(golden)
            # Store for use in Step 1 context block below
            _golden_warm_ctx = warm_ctx
            _golden_warm_id = golden.run_id
        else:
            _golden_warm_ctx = None
            _golden_warm_id = None
    else:
        _golden_warm_ctx = None
        _golden_warm_id = None

    # Step 0: Guardrail pre-check
    pre = await guardrail_engine.pre_check(user_id, input_text, router=_router)
    if pre.verdict == "block":
        exc = GuardrailBlocked(pre, "pre_check")
        yield {"type": "error", "exc": exc, "data": {"detail": str(pre)}}
        return

    # Step 1: Retrieve relevant context (+ inject golden warm-start seed if available)
    # Phase 18: Agentic RAG (CRAG-lite) over the FAISS corpus + memory; falls back to
    # past-run knowledge when disabled or empty.
    rag_block = ""
    if settings.agentic_rag_enabled:
        try:
            from ..rag.agentic import agentic_retrieve
            rag_block = await agentic_retrieve(
                input_text, _router, identity_id=user_id, user_id=user_id
            )
        except Exception:  # noqa: BLE001
            rag_block = ""
    if not rag_block:
        past_context = knowledge_engine.get_relevant_context(input_text, top_k=3)
        if past_context:
            lines = []
            for i, run_info in enumerate(past_context, 1):
                lines.append(
                    f"[Prior Run {i} — {run_info['domain']}, model: {run_info['model']}, "
                    f"relevance: {run_info['score']:.2f}]"
                )
                lines.append(run_info["output"][:300])
            rag_block = "\n\n".join(lines)

    parts = [p for p in (_golden_warm_ctx, rag_block) if p]
    context_block = "\n\n".join(parts)

    # Step 2: Learned model routing
    best_model = knowledge_engine.get_best_model_for(input_text)

    task_ctx = TaskContext(
        task_id=task_id,
        domain=domain,
        input=input_text,
        metadata={
            "retrieved_context": context_block,
            "recommended_model": best_model,
            "user_id": user_id,
            "_guardrail_checked": True,  # F-018
            "router": _router,
        },
    )

    # Step 3: Stream agent pipeline — yield each message as it completes
    messages: list[AgentMessage] = []
    async for msg in bus.stream_collaboration(task_ctx, pipeline):
        messages.append(msg)
        yield {
            "type": "agent_message",
            "data": {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
                "timestamp": msg.timestamp,
                "message_id": msg.message_id,
                "summary": "",
            },
        }

    serialized = [
        {
            "role": m.role,
            "content": m.content,
            "metadata": m.metadata,
            "timestamp": m.timestamp,
            "message_id": m.message_id,
        }
        for m in messages
    ]

    # Step 4: Score
    final_output = messages[-1].content if messages else ""
    model_used = messages[-1].metadata.get("model", "unknown") if messages else "unknown"

    try:
        scores = await rubric_score(input_text, final_output)
    except Exception:
        scores = {}

    # Step 4b: Post-guardrail
    post = await guardrail_engine.post_check(user_id, final_output, router=_router)
    if post.verdict == "block":
        exc = GuardrailBlocked(post, "post_check")
        yield {"type": "error", "exc": exc, "data": {"detail": str(post)}}
        return

    # Step 4c: Summaries + verdict
    try:
        summaries = await summarize_run(input_text, serialized, final_output, router=_router)
    except Exception:
        summaries = {"run_summary": "", "per_agent": {}}
    per_agent_summaries: dict[str, str] = summaries.get("per_agent", {})
    for msg in serialized:
        msg["summary"] = per_agent_summaries.get(msg["message_id"], "")
    run_summary: str = summaries.get("run_summary", "")
    verdict = derive_verdict(scores)

    # Step 4d: Promote to golden cache if quality threshold met
    try:
        golden_cache.promote(
            run_id=task_id,
            input_text=input_text,
            final_answer=final_output,
            scores=scores,
            verdict=verdict,
            messages=serialized,
            embedding=query_emb if match is not None else embed_text(input_text),
        )
    except Exception:
        pass  # promotion failure must never break a run

    # Step 5: Feed back into knowledge engine
    graph_state = knowledge_engine.ingest_run(
        input_text=input_text,
        output=final_output,
        domain=domain,
        model_used=model_used,
        scores=scores,
    )

    yield {
        "type": "complete",
        "data": {
            "task_id": task_id,
            "domain": domain,
            "pipeline": pipeline,
            "messages": serialized,
            "scores": scores,
            "model_used": model_used,
            "knowledge_graph": graph_state,
            "run_summary": run_summary,
            "final_answer": final_output,
            "verdict": verdict,
        },
    }
