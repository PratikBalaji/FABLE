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
from .concurrency import identity_slot
from .guardrails import GuardrailBlocked, guardrail_engine
from .knowledge_engine import knowledge_engine
from .memory_service import memory_service
from .summarizer import summarize_run
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


async def _run_rounds_asyncio(
    task_ctx: "TaskContext",
    round_roles: list[str],
    max_rounds: int,
    *,
    task_id: str,
) -> tuple[list["AgentMessage"], dict, int]:
    """Native AgentBus round loop (default orchestrator / baseline).

    Returns (round_messages, judge_result, rounds_completed). The Planner is NOT run
    here — the caller runs it once before invoking any orchestrator. Roles within a
    round form a width-1 dependency DAG (critic←actor, validator←critic, refiner←
    validator), so they run sequentially by design.
    """
    round_msgs: list[AgentMessage] = []
    judge_result: dict = {}
    rounds_completed = 0

    for round_num in range(max_rounds):
        task_ctx.metadata["adversarial_round"] = round_num
        log.info("adversarial_round_start", task_id=task_id, round=round_num + 1, max=max_rounds)

        for role in round_roles:
            msg = await bus.dispatch(role, task_ctx)
            round_msgs.append(msg)

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

    return round_msgs, judge_result, rounds_completed


async def run_adversarial_task(
    input_text: str,
    domain: str,
    max_rounds: int | None = None,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    router: "ModelRouter | None" = None,
) -> dict:
    """Public entry — wraps the run in a per-identity concurrency slot (F-035).

    Phase 19: when adversarial_ensemble_size > 1, runs N independent debates
    concurrently and returns the highest-scoring one (run-level self-consistency).
    The whole ensemble shares one concurrency slot.
    """
    async with identity_slot(user_id):
        ensemble_size = max(1, settings.adversarial_ensemble_size)
        if ensemble_size == 1:
            return await _run_adversarial_task(
                input_text, domain, max_rounds,
                user_id=user_id, session_id=session_id, router=router,
            )
        return await _run_adversarial_ensemble(
            input_text, domain, max_rounds, ensemble_size,
            user_id=user_id, session_id=session_id, router=router,
        )


async def _run_adversarial_ensemble(
    input_text: str,
    domain: str,
    max_rounds: int | None,
    ensemble_size: int,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    router: "ModelRouter | None" = None,
) -> dict:
    """Run N independent adversarial debates in parallel; reduce to the best by judge_score.

    Each debate builds its own TaskContext (separate history) so there is no shared
    mutable state across the gathered coroutines. The reducer selects the candidate with
    the highest adversarial_meta.judge_score (tie-break: lowest index) and attaches
    ensemble_meta describing the full candidate set.
    """
    import asyncio

    log.info("adversarial_ensemble_started", size=ensemble_size, domain=domain)

    # Pass session_id=None to every branch: chat-turn persistence is gated on session_id
    # inside _run_adversarial_task, and we must not write N duplicate turns. Consequence:
    # in ensemble mode the linked assistant chat turn is skipped (the full transcript is
    # still persisted via store_adversarial_run). Ensemble is a benchmark/research path;
    # interactive chat uses ensemble_size=1, which keeps the original persistence intact.
    tasks = [
        _run_adversarial_task(
            input_text, domain, max_rounds,
            user_id=user_id, session_id=None, router=router,
        )
        for _ in range(ensemble_size)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates = [r for r in results if isinstance(r, dict)]
    if not candidates:
        # All debates failed — re-raise the first exception for the caller/route to map.
        first_exc = next((r for r in results if isinstance(r, BaseException)), None)
        raise first_exc if first_exc else RuntimeError("ensemble produced no results")

    def _score(r: dict) -> float:
        return float(r.get("adversarial_meta", {}).get("judge_score", 0.0) or 0.0)

    winner_idx, winner = max(enumerate(candidates), key=lambda iv: _score(iv[1]))

    winner["ensemble_meta"] = {
        "ensemble_size": ensemble_size,
        "completed": len(candidates),
        "failed": ensemble_size - len(candidates),
        "winner_index": winner_idx,
        "candidate_scores": [_score(c) for c in candidates],
    }
    log.info(
        "adversarial_ensemble_done",
        size=ensemble_size,
        completed=len(candidates),
        winner_index=winner_idx,
        winner_score=_score(winner),
    )
    return winner


async def _run_adversarial_task(
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
    _MAX_ROUNDS_CAP = 10  # F-020: hard ceiling regardless of caller
    if max_rounds is None:
        max_rounds = settings.adversarial_max_rounds
    max_rounds = min(max_rounds, _MAX_ROUNDS_CAP)

    task_id = str(uuid.uuid4())
    multiuser = bool(settings.use_supabase and user_id)
    log.info("adversarial_task_started", task_id=task_id, domain=domain, max_rounds=max_rounds)

    # Guardrail pre-check on user input
    pre = await guardrail_engine.pre_check(user_id, input_text, router=router)
    if pre.verdict == "block":
        raise GuardrailBlocked(pre, "pre_check")

    # Retrieve context: Phase 18 Agentic RAG (CRAG-lite) over FAISS corpus + memory.
    # Falls back to pgvector grouped memory (multi-user) or past-run knowledge (legacy).
    context_block = ""
    if settings.agentic_rag_enabled:
        try:
            from ..rag.agentic import agentic_retrieve
            context_block = await agentic_retrieve(
                input_text, router, identity_id=user_id, user_id=user_id
            )
        except Exception:  # noqa: BLE001
            context_block = ""

    if not context_block:
        if multiuser:
            assert user_id is not None
            context_block = await memory_service.grouped_context(user_id, input_text)
        else:
            past_context = knowledge_engine.get_relevant_context(input_text, top_k=3)
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
            "user_id": user_id,
            "_guardrail_checked": True,  # F-018: pre_check already ran above
        },
    )

    # Use ELM-driven round roles if available, else static default
    round_roles = declarations.active_round_roles() or _ROUND_ROLES

    all_messages: list[AgentMessage] = []

    # Planner runs exactly once — sets strategy for all rounds
    planner_msg = await bus.dispatch("adv:planner", task_ctx)
    all_messages.append(planner_msg)
    log.info("adversarial_planner_done", task_id=task_id)

    # Phase 19: the round loop is the only thing that differs between orchestrators.
    # Everything around it (RAG, guardrails, scoring, persistence) is shared, so the
    # asyncio-vs-langgraph comparison isolates exactly the orchestration layer.
    if settings.orchestrator == "langgraph":
        try:
            from ..graph.adversarial_graph import run_rounds_langgraph
        except ImportError:  # optional dep absent → native loop (no dispatch happened yet)
            log.warning("langgraph_not_installed_fallback_asyncio")
            round_msgs, judge_result, rounds_completed = await _run_rounds_asyncio(
                task_ctx, round_roles, max_rounds, task_id=task_id,
            )
        else:
            # Runtime errors here propagate — do NOT re-run (would double-dispatch the loop).
            round_msgs, judge_result, rounds_completed = await run_rounds_langgraph(
                task_ctx, round_roles, max_rounds, task_id=task_id,
            )
    else:
        round_msgs, judge_result, rounds_completed = await _run_rounds_asyncio(
            task_ctx, round_roles, max_rounds, task_id=task_id,
        )
    all_messages.extend(round_msgs)

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

    # Summaries (concurrent, non-fatal)
    try:
        summaries = await summarize_run(input_text, serialized, final_output, router=router)
    except Exception:
        summaries = {"run_summary": "", "per_agent": {}}
    per_agent_summaries: dict[str, str] = summaries.get("per_agent", {})
    for msg in serialized:
        msg["summary"] = per_agent_summaries.get(msg["message_id"], "")
    run_summary: str = summaries.get("run_summary", "")

    # Verdict mirrors adversarial judge
    verdict = {
        "verdict": adversarial_meta["judge_verdict"],
        "score": adversarial_meta["judge_score"],
        "rationale": adversarial_meta["judge_rationale"],
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
            router=router,  # F-010: pass router for abstract_for_memory
        )
        if session_id:
            await memory_service.store_chat_turn(
                user_id, session_id, "user", input_text, router=router,
            )
            await memory_service.store_chat_turn(
                user_id, session_id, "assistant", final_output,
                model_used=model_used, scores=scores, adversarial_run_id=run_id,
                router=router,
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
        "run_summary": run_summary,
        "final_answer": final_output,
        "verdict": verdict,
    }


def _balanced_json_objects(text: str) -> list[str]:
    """Return every top-level balanced {...} substring, in document order.

    Brace-depth scan that respects strings + escapes, so braces inside string
    values don't throw off nesting. Used to find the Judge's trailing verdict
    object even when earlier (e.g. Actor-embedded) JSON appears first (F-019).
    """
    objects: list[str] = []
    depth = 0
    start = -1
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(text[start : i + 1])
                    start = -1
    return objects


def _parse_judge_output(content: str) -> dict:
    """Extract and parse JSON from Judge output. Handles markdown fences."""
    # Strip common markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # F-019: the Judge's verdict is its FINAL output. A greedy first-match `{...}` can
    # latch onto JSON the Actor embedded earlier in the transcript. Scan ALL balanced
    # objects and prefer the LAST parseable one that actually carries a "verdict" key.
    candidates = _balanced_json_objects(cleaned)
    chosen: dict | None = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            chosen = obj  # keep last verdict-bearing object
    if chosen is not None:
        return chosen

    # P14: field-level salvage — the judge JSON is frequently TRUNCATED mid-string
    # (long final_answer hits the token cap), which nukes a perfectly good verdict.
    # Recover verdict/score/rationale individually via regex rather than defaulting
    # to REJECT/0.0, which silently discarded valid ACCEPT decisions.
    salvaged = _salvage_judge_fields(cleaned)
    if salvaged is not None:
        log.warning("adversarial_judge_parse_salvaged", verdict=salvaged.get("verdict"))
        return salvaged

    log.warning("adversarial_judge_parse_failed", content_preview=content[:200])
    return {
        "verdict": "REJECT",
        "score": 0.0,
        "rationale": "Judge output could not be parsed as JSON.",
        "unresolved_issues": ["Judge parse failure"],
        "final_answer": "",
    }


def _salvage_judge_fields(text: str) -> dict | None:
    """Extract judge fields individually when the full JSON is malformed/truncated.

    Returns a dict if at least a verdict was recovered, else None.
    """
    verdict_m = re.search(r'"verdict"\s*:\s*"(ACCEPT|REJECT)"', text, re.IGNORECASE)
    if not verdict_m:
        return None
    verdict = verdict_m.group(1).upper()

    score_m = re.search(r'"score"\s*:\s*([0-9]*\.?[0-9]+)', text)
    score = float(score_m.group(1)) if score_m else (0.8 if verdict == "ACCEPT" else 0.0)

    rationale_m = re.search(r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    rationale = rationale_m.group(1).replace('\\"', '"').replace("\\n", " ") if rationale_m else \
        "Recovered from truncated judge output."

    # final_answer may be truncated (no closing quote) — grab whatever is present.
    fa_m = re.search(r'"final_answer"\s*:\s*"((?:[^"\\]|\\.)*)', text)
    final_answer = fa_m.group(1).replace('\\"', '"').replace("\\n", "\n") if fa_m else ""

    return {
        "verdict": verdict,
        "score": score,
        "rationale": rationale,
        "unresolved_issues": [],
        "final_answer": final_answer,
    }


def _judge_model(messages: list[AgentMessage]) -> str:
    """Return the model identifier used by the Judge agent."""
    for m in reversed(messages):
        if m.role == "adv:judge":
            return m.metadata.get("model", "unknown")
    return messages[-1].metadata.get("model", "unknown") if messages else "unknown"
