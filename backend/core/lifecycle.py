"""
Lifecycle orchestrator — wires the agent bus, knowledge engine, and learned
model router into a single run that accumulates knowledge over time.
"""
from __future__ import annotations

import uuid

from .bus import AgentMessage, TaskContext, bus
from .knowledge_engine import knowledge_engine
from ..evaluation.rubric import score as rubric_score


async def run_task(
    input_text: str,
    domain: str,
    pipeline: list[str] | None = None,
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
    if pipeline is None:
        pipeline = ["analyst", "critic", "synthesizer"]

    task_id = str(uuid.uuid4())

    # Step 1: Retrieve relevant context from past knowledge
    past_context = knowledge_engine.get_relevant_context(input_text, top_k=3)
    context_block = ""
    if past_context:
        lines = []
        for i, run_info in enumerate(past_context, 1):
            lines.append(f"[Prior Run {i} — {run_info['domain']}, model: {run_info['model']}, relevance: {run_info['score']:.2f}]")
            lines.append(run_info["output"][:300])
        context_block = "\n\n".join(lines)

    # Step 2: Learned model routing
    best_model = knowledge_engine.get_best_model_for(input_text)

    task_ctx = TaskContext(
        task_id=task_id,
        domain=domain,
        input=input_text,
        metadata={
            "retrieved_context": context_block,
            "recommended_model": best_model,
        },
    )

    # Step 3: Run agent pipeline
    messages: list[AgentMessage] = await bus.run_collaboration(task_ctx, pipeline)

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

    # Step 4: Score the final output
    final_output = messages[-1].content if messages else ""
    model_used = messages[-1].metadata.get("model", "unknown") if messages else "unknown"

    try:
        scores = await rubric_score(input_text, final_output)
    except Exception:
        scores = {}

    # Step 5: Feed back into knowledge engine
    graph_state = knowledge_engine.ingest_run(
        input_text=input_text,
        output=final_output,
        domain=domain,
        model_used=model_used,
        scores=scores,
    )

    return {
        "task_id": task_id,
        "domain": domain,
        "pipeline": pipeline,
        "messages": serialized,
        "scores": scores,
        "model_used": model_used,
        "knowledge_graph": graph_state,
    }
