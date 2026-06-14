"""POST /run + POST /run/stream — orchestrator entrypoints.

P4a wiring:
  - Identity dependency (cookie or auth) resolves identity_id.
  - BYOK (F-015): if user has a stored credential, a per-request ModelRouter is
    constructed from it; falls back to the server's global key.
  - PII redaction runs BEFORE the pipeline; output is reinjected before return.
  - /run/stream emits SSE events (agent_message per agent, complete at end).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from ..schemas import RunRequest, RunResponse, AgentMessageOut, GraphState, AdversarialRunResponse, AdversarialMeta, VerdictMeta, RecycledMeta
from ...core.auth import AuthedUser, get_optional_user
from ...core.config import settings
from ...core.concurrency import ConcurrencyLimitExceeded
from ...core.credentials import resolve_credential
from ...core.guardrails import GuardrailBlocked
from ...core.identity import resolve_identity, set_identity_cookie
from ...core.lifecycle import run_task, run_task_streaming
from ...core.adversarial_lifecycle import run_adversarial_task
from ...core.pii import PiiRedactionFailed, persist_entity_map, redact, reinject
from ...router.model_router import ModelRouter, router as default_router
from ..limiter import limiter

router = APIRouter()


def _require_csrf(x_fable_request: str = Header(default="")) -> None:
    """F-008: Block plain form-based CSRF by requiring a custom header browsers
    cannot add on cross-origin form submissions."""
    if x_fable_request != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF header X-FABLE-Request: 1",
        )


async def _resolve_router(auth: AuthedUser | None) -> ModelRouter:
    """F-015: return per-user BYOK router if credentials exist; else global router."""
    if settings.use_supabase and auth:
        try:
            cred = await resolve_credential(auth.id)
            if cred:
                return ModelRouter(api_key=cred.api_key, base_url=cred.base_url)
        except Exception:
            pass  # non-fatal — fall back to server key
    return default_router


@limiter.limit(settings.rate_limit_run)
@router.post("/run", response_model=RunResponse)
async def run_collaboration(
    req: RunRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
    _csrf: None = Depends(_require_csrf),
) -> RunResponse:
    identity_id: str | None = None
    session_id: str | None = getattr(req, "session_id", None)

    # Identity resolution (multi-user only)
    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    # BYOK — per-user router if available
    active_router = await _resolve_router(auth)

    # PII redaction (in)
    try:
        redaction = await redact(req.input, router=active_router)
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

    # Lifecycle
    try:
        result = await run_task(
            input_text=input_for_pipeline,
            domain=req.domain,
            pipeline=req.pipeline,
            user_id=identity_id,
            router=active_router,
        )
    except ConcurrencyLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error": "concurrency_limit", "reason": str(exc)})
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
        m2["summary"] = reinject(m2.get("summary", ""), redaction.entities)
        reinjected_messages.append(m2)

    raw_verdict = result.get("verdict", {})

    meta = result.get("metadata", {})
    return RunResponse(
        task_id=result["task_id"],
        domain=result["domain"],
        pipeline=result["pipeline"],
        messages=[AgentMessageOut(**m) for m in reinjected_messages],
        scores=result.get("scores", {}),
        model_used=result.get("model_used", ""),
        knowledge_graph=GraphState(**result["knowledge_graph"]),
        run_summary=reinject(result.get("run_summary", ""), redaction.entities),
        final_answer=reinject(result.get("final_answer", ""), redaction.entities),
        verdict=VerdictMeta(**raw_verdict) if raw_verdict else VerdictMeta(),
        recycled_meta=RecycledMeta(
            recycled=bool(meta.get("recycled")),
            golden_run_id=str(meta.get("golden_run_id") or ""),
            similarity=float(meta.get("similarity") or 0.0),
        ),
    )


@limiter.limit(settings.rate_limit_run)
@router.post("/run/stream")
async def run_collaboration_stream(
    req: RunRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
    _csrf: None = Depends(_require_csrf),
) -> EventSourceResponse:
    """SSE streaming variant of /run.

    Events:
      data: {"type":"agent_message", "role":..., "content":..., ...}  — one per agent
      data: {"type":"complete", "task_id":..., "scores":..., ...}     — final state
      data: {"type":"error", "detail":...}                            — on failure
    """
    identity_id: str | None = None
    session_id: str | None = getattr(req, "session_id", None)

    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    active_router = await _resolve_router(auth)

    try:
        redaction = await redact(req.input, router=active_router)
    except PiiRedactionFailed as exc:
        async def _err():
            yield {"data": json.dumps({"type": "error", "detail": f"pii_redaction_failed: {exc}"})}
        return EventSourceResponse(_err())

    input_for_pipeline = redaction.redacted

    if settings.use_supabase and session_id and redaction.entities:
        try:
            persist_entity_map(redaction.entities, session_id, task_id="pending")
        except Exception:
            pass

    async def generate():
        try:
            stream = await run_task_streaming(
                input_text=input_for_pipeline,
                domain=req.domain,
                pipeline=req.pipeline,
                user_id=identity_id,
                router=active_router,
            )
            async for event in stream:
                if event["type"] == "error":
                    yield {"data": json.dumps({"type": "error", "detail": str(event.get("data", {}))})}
                    return
                elif event["type"] == "agent_message":
                    msg = event["data"]
                    msg["content"] = reinject(msg.get("content", ""), redaction.entities)
                    yield {"data": json.dumps({"type": "agent_message", **msg})}
                elif event["type"] == "complete":
                    d = event["data"]
                    yield {"data": json.dumps({
                        "type": "complete",
                        "task_id": d["task_id"],
                        "domain": d["domain"],
                        "pipeline": d["pipeline"],
                        "scores": d.get("scores", {}),
                        "model_used": d.get("model_used", ""),
                        "knowledge_graph": d["knowledge_graph"],
                        "run_summary": reinject(d.get("run_summary", ""), redaction.entities),
                        "final_answer": reinject(d.get("final_answer", ""), redaction.entities),
                        "verdict": d.get("verdict", {}),
                    })}
        except GuardrailBlocked as exc:
            yield {"data": json.dumps({"type": "error", "detail": f"guardrail_blocked: {exc.stage}"})}
        except Exception as exc:  # noqa: BLE001
            yield {"data": json.dumps({"type": "error", "detail": str(exc)})}

    return EventSourceResponse(generate())


@limiter.limit(settings.rate_limit_adv)
@router.post("/adversarial-run", response_model=AdversarialRunResponse)
async def run_adversarial_collaboration(
    req: RunRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
    _csrf: None = Depends(_require_csrf),
) -> AdversarialRunResponse:
    """Run the 6-stage adversarial pipeline (Planner→Actor→Critic→Validator→Refiner→Judge)."""
    identity_id: str | None = None
    session_id: str | None = getattr(req, "session_id", None)

    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    active_router = await _resolve_router(auth)

    # PII redaction (in)
    try:
        redaction = await redact(req.input, router=active_router)
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
            router=active_router,
        )
    except ConcurrencyLimitExceeded as exc:
        raise HTTPException(status_code=429, detail={"error": "concurrency_limit", "reason": str(exc)})
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
        m2["summary"] = reinject(m2.get("summary", ""), redaction.entities)
        reinjected_messages.append(m2)

    adv_meta = result.get("adversarial_meta", {})
    raw_verdict = result.get("verdict", {})

    return AdversarialRunResponse(
        task_id=result["task_id"],
        domain=result["domain"],
        pipeline=result["pipeline"],
        messages=[AgentMessageOut(**m) for m in reinjected_messages],
        scores=result.get("scores", {}),
        model_used=result.get("model_used", ""),
        knowledge_graph=GraphState(**result["knowledge_graph"]),
        run_summary=reinject(result.get("run_summary", ""), redaction.entities),
        final_answer=reinject(result.get("final_answer", ""), redaction.entities),
        verdict=VerdictMeta(**raw_verdict) if raw_verdict else VerdictMeta(),
        adversarial_meta=AdversarialMeta(
            rounds_completed=adv_meta.get("rounds_completed", 0),
            max_rounds=adv_meta.get("max_rounds", 2),
            judge_verdict=adv_meta.get("judge_verdict", "UNKNOWN"),
            judge_score=adv_meta.get("judge_score", 0.0),
            judge_rationale=adv_meta.get("judge_rationale", ""),
            unresolved_issues=adv_meta.get("unresolved_issues", []),
        ),
    )
