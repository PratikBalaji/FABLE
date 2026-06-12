"""
Adversarial lifecycle — iterative multi-LLM collaboration with Judge-controlled termination.

Pipeline per round:
    adv:actor → adv:critic → adv:validator → adv:refiner → adv:judge

The Planner runs once before the loop. The Judge outputs JSON with a verdict field:
  "ACCEPT" → terminate, use judge.final_answer as the user-facing output
  "REJECT" → run another round (up to max_rounds)

On the final round the Judge's system prompt forces an ACCEPT, guaranteeing termination.
"""
from __future__ import annotations

import json
import re
import uuid

import structlog

from .bus import AgentMessage, TaskContext, bus
from .guardrails import GuardrailBlocked, guardrail_engine
from .knowledge_engine import knowledge_engine
from .memory_service import memory_service
from ..evaluation.rubric import score as rubric_score
from ..elm.fallback import static_declarations
from ..router.model_router import ModelRouter
from .config import settings

log = structlog.get_logger()

# Default roles dispatched once per round (excluding Planner).
# When ELM is active, this is replaced by PipelineDeclaration.active_round_roles().
_ROUND_ROLES = ["adv:actor", "adv:critic", "adv:validator", "adv:refiner", "adv:judge"]


def _get_declarations(input_text: str, domain: str):
    """
    Generate pipeline declarations via ELM (if enabled) or static fallback.

    Returns a PipelineDeclaration with role configs and the active round roles list.
    """
    if settings.elm_enabled:
        try:
            from ..elm.engine import get_elm_engine
            elm = get_elm_engine()
            if elm is not None:
                declarations = elm.generate_declarations(input_text, domain)
                log.info("elm_declarations_generated", domain=domain, model=declarations.elm_model)
                return declarations
        except Exception:
            log.warning("elm_fallback", reason="inference_failed", exc_info=True)

    return static_declarations(domain=domain, task_input=input_text)


async def run_adversarial_task(
    input_text: str,
    domain: str,
    max_rounds: int | None = None,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    router: "ModelRouter | None" = None,
) -> dict:
    """
    Execute an adversarial multi-LLM collaboration.

    Returns a dict with the same keys as run_task() plus 'adversarial_meta'.
    """
    if max_rounds is None:
        max_rounds = settings.adversarial_max_rounds

    task_id = str(uuid.uuid4())
    multiuser = bool(settings.use_supabase and user_id)
    log.info("adversarial_task_started", task_id=task_id, domain=domain, max_rounds=max_rounds)

    # Guardrail pre-check on user input
    pre = await guardrail_engine.pre_check(user_id, input_text, router=router)
    if pre.verdict == "block":
        raise GuardrailBlocked(pre, "pre_check")

    # Retrieve context: per-user semantic memory (multi-user) or global file engine (legacy).
    if multiuser:
        assert user_id is not None
        context_block = await memory_service.grouped_context(user_id, input_text)
    else:
        past_context = knowledge_engine.get_relevant_context(input_text, top_k=3)
        context_block = ""
        if past_context:
            lines = []
            for i, run_info in enumerate(past_context, 1):
                lines.append(
                    f"[Prior Run {i} — {run_info['domain']}, model: {run_info['model']}, "
                    f"relevance: {run_info['score']:.2f}]"
                )
                lines.append(run_info["output"][:300])
            context_block = "\n\n".join(lines)

    # Generate ELM declarations (or static fallback)
    declarations = _get_declarations(input_text, domain)

    task_ctx = TaskContext(
        task_id=task_id,
        domain=domain,
        input=input_text,
        metadata={
            "retrieved_context": context_block,
            "adversarial_max_rounds": max_rounds,
            "adversarial_round": 0,
            "router": router,  # per-user router; None => agents use singleton fallback
            "elm_declarations": declarations,
        },
    )

    # Use ELM-driven round roles if available, else static default
    round_roles = declarations.active_round_roles() or _ROUND_ROLES

    all_messages: list[AgentMessage] = []
    judge_result: dict = {}
    rounds_completed = 0

    # Planner runs exactly once — sets strategy for all rounds
    planner_msg = await bus.dispatch("adv:planner", task_ctx)
    all_messages.append(planner_msg)
    log.info("adversarial_planner_done", task_id=task_id)

    # Adversarial loop
    for round_num in range(max_rounds):
        task_ctx.metadata["adversarial_round"] = round_num
        log.info("adversarial_round_start", task_id=task_id, round=round_num + 1, max=max_rounds)

        for role in round_roles:
            msg = await bus.dispatch(role, task_ctx)
            all_messages.append(msg)

            if role == "adv:judge":
                judge_result = _parse_judge_output(msg.content)
                rounds_completed = round_num + 1
                log.info(
                    "adversarial_judge_verdict",
                    task_id=task_id,
                    round=round_num + 1,
                    verdict=judge_result.get("verdict"),
                    score=judge_result.get("score"),
                )
                if judge_result.get("verdict") == "ACCEPT":
                    break

        if judge_result.get("verdict") == "ACCEPT":
            break

    # Determine final output
    if judge_result.get("verdict") == "ACCEPT" and judge_result.get("final_answer", "").strip():
        final_output = judge_result["final_answer"]
    else:
        # Fallback: last Actor output
        final_output = next(
            (m.content for m in reversed(all_messages) if m.role == "adv:actor"), ""
        )

    model_used = _judge_model(all_messages)

    try:
        scores = await rubric_score(input_text, final_output)
    except Exception:
        scores = {}

    # Guardrail post-check (credential-leak only)
    post = await guardrail_engine.post_check(user_id, final_output, router=router)
    if post.verdict == "block":
        raise GuardrailBlocked(post, "post_check")

    graph_state = knowledge_engine.ingest_run(
        input_text=input_text,
        output=final_output,
        domain=domain,
        model_used=model_used,
        scores=scores,
    )

    serialized = [
        {
            "role": m.role,
            "content": m.content,
            "metadata": m.metadata,
            "timestamp": m.timestamp,
            "message_id": m.message_id,
        }
        for m in all_messages
    ]

    # Reconstruct pipeline list for response metadata
    pipeline_used = ["adv:planner"] + _ROUND_ROLES * rounds_completed

    adversarial_meta = {
        "rounds_completed": rounds_completed,
        "max_rounds": max_rounds,
        "judge_verdict": judge_result.get("verdict", "UNKNOWN"),
        "judge_score": judge_result.get("score", 0.0),
        "judge_rationale": judge_result.get("rationale", ""),
        "unresolved_issues": judge_result.get("unresolved_issues", []),
    }

    # Persist per-user memory: full transcript + a linked assistant chat turn (multi-user mode).
    if multiuser:
        assert user_id is not None
        run_id = await memory_service.store_adversarial_run(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            domain=domain,
            input_text=input_text,
            final_output=final_output,
            adversarial_meta=adversarial_meta,
            scores=scores,
            pipeline=pipeline_used,
            model_used=model_used,
            messages=serialized,
        )
        if session_id:
            await memory_service.store_chat_turn(user_id, session_id, "user", input_text)
            await memory_service.store_chat_turn(
                user_id, session_id, "assistant", final_output,
                model_used=model_used, scores=scores, adversarial_run_id=run_id,
            )

    log.info(
        "adversarial_task_done",
        task_id=task_id,
        rounds=rounds_completed,
        verdict=judge_result.get("verdict", "UNKNOWN"),
    )

    return {
        "task_id": task_id,
        "domain": domain,
        "pipeline": pipeline_used,
        "messages": serialized,
        "scores": scores,
        "model_used": model_used,
        "knowledge_graph": graph_state,
        "adversarial_meta": adversarial_meta,
    }


def _parse_judge_output(content: str) -> dict:
    """Extract and parse JSON from Judge output. Handles markdown fences."""
    # Strip common markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: find first JSON object anywhere in the string
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    log.warning("adversarial_judge_parse_failed", content_preview=content[:200])
    return {
        "verdict": "REJECT",
        "score": 0.0,
        "rationale": "Judge output could not be parsed as JSON.",
        "unresolved_issues": ["Judge parse failure"],
        "final_answer": "",
    }


def _judge_model(messages: list[AgentMessage]) -> str:
    """Return the model identifier used by the Judge agent."""
    for m in reversed(messages):
        if m.role == "adv:judge":
            return m.metadata.get("model", "unknown")
    return messages[-1].metadata.get("model", "unknown") if messages else "unknown"
