"""POST /run — orchestrator entrypoint.

P4a wiring:
  - Identity dependency (cookie or auth) resolves identity_id.
  - PII redaction runs BEFORE the pipeline; output is reinjected before return.
  - Multi-user mode (USE_SUPABASE=true): identity is required.
  - Legacy single-user mode: PII still applies if pii_enabled; no DB writes.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..schemas import RunRequest, RunResponse, AgentMessageOut, GraphState, AdversarialRunResponse, AdversarialMeta
from ...core.auth import AuthedUser, get_optional_user
from ...core.config import settings
from ...core.guardrails import GuardrailBlocked
from ...core.identity import resolve_identity, set_identity_cookie
from ...core.lifecycle import run_task
from ...core.adversarial_lifecycle import run_adversarial_task
from ...core.pii import PiiRedactionFailed, persist_entity_map, redact, reinject
from ...router.model_router import router as default_router

router = APIRouter()


@router.post("/run", response_model=RunResponse)
async def run_collaboration(
    req: RunRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
) -> RunResponse:
    identity_id: str | None = None
    session_id: str | None = getattr(req, "session_id", None)

    # Identity resolution (multi-user only)
    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    # PII redaction (in)
    try:
        redaction = await redact(req.input, router=default_router)
    except PiiRedactionFailed as exc:
        raise HTTPException(
            500,
            detail={"error": "pii_redaction_failed", "reason": str(exc)},
        )
    input_for_pipeline = redaction.redacted

    # Persist entity map for the session/task (only if we have a session)
    if settings.use_supabase and session_id and redaction.entities:
        # task_id assigned by lifecycle; we don't know it yet — use a temp str.
        # The persisted map is session-scoped + 7-day TTL; precise task_id linkage
        # is captured by reinjecting from in-memory map (below).
        try:
            persist_entity_map(redaction.entities, session_id, task_id="pending")
        except Exception:
            pass  # non-fatal — in-memory reinjection still works

    # Lifecycle
    try:
        result = await run_task(
            input_text=input_for_pipeline,
            domain=req.domain,
            pipeline=req.pipeline,
            user_id=identity_id,
        )
    except GuardrailBlocked as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "guardrail_blocked",
                "stage": exc.stage,
                "category": exc.result.category,
                "reason": exc.result.reason,
                "layer": exc.result.layer,
            },
        )

    # PII reinjection (out) — restore real names in user-facing output
    reinjected_messages = []
    for m in result["messages"]:
        m2 = dict(m)
        m2["content"] = reinject(m2.get("content", ""), redaction.entities)
        reinjected_messages.append(m2)

    return RunResponse(
        task_id=result["task_id"],
        domain=result["domain"],
        pipeline=result["pipeline"],
        messages=[AgentMessageOut(**m) for m in reinjected_messages],
        scores=result.get("scores", {}),
        model_used=result.get("model_used", ""),
        knowledge_graph=GraphState(**result["knowledge_graph"]),
    )


@router.post("/adversarial-run", response_model=AdversarialRunResponse)
async def run_adversarial_collaboration(
    req: RunRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
) -> AdversarialRunResponse:
    """Run the 6-stage adversarial pipeline (Planner→Actor→Critic→Validator→Refiner→Judge)."""
    identity_id: str | None = None
    session_id: str | None = getattr(req, "session_id", None)

    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    # PII redaction (in)
    try:
        redaction = await redact(req.input, router=default_router)
    except PiiRedactionFailed as exc:
        raise HTTPException(
            500,
            detail={"error": "pii_redaction_failed", "reason": str(exc)},
        )
    input_for_pipeline = redaction.redacted

    if settings.use_supabase and session_id and redaction.entities:
        try:
            persist_entity_map(redaction.entities, session_id, task_id="pending")
        except Exception:
            pass

    # Adversarial lifecycle
    try:
        result = await run_adversarial_task(
            input_text=input_for_pipeline,
            domain=req.domain,
            user_id=identity_id,
            session_id=session_id,
            router=default_router,
        )
    except GuardrailBlocked as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "guardrail_blocked",
                "stage": exc.stage,
                "category": exc.result.category,
                "reason": exc.result.reason,
                "layer": exc.result.layer,
            },
        )

    # PII reinjection (out)
    reinjected_messages = []
    for m in result["messages"]:
        m2 = dict(m)
        m2["content"] = reinject(m2.get("content", ""), redaction.entities)
        reinjected_messages.append(m2)

    adv_meta = result.get("adversarial_meta", {})

    return AdversarialRunResponse(
        task_id=result["task_id"],
        domain=result["domain"],
        pipeline=result["pipeline"],
        messages=[AgentMessageOut(**m) for m in reinjected_messages],
        scores=result.get("scores", {}),
        model_used=result.get("model_used", ""),
        knowledge_graph=GraphState(**result["knowledge_graph"]),
        adversarial_meta=AdversarialMeta(
            rounds_completed=adv_meta.get("rounds_completed", 0),
            max_rounds=adv_meta.get("max_rounds", 2),
            judge_verdict=adv_meta.get("judge_verdict", "UNKNOWN"),
            judge_score=adv_meta.get("judge_score", 0.0),
            judge_rationale=adv_meta.get("judge_rationale", ""),
            unresolved_issues=adv_meta.get("unresolved_issues", []),
        ),
    )
