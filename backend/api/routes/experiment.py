"""POST /experiment/run — Monte Carlo prompt robustness experiment (Phase 13)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from ..schemas import MonteCarloRequest, MonteCarloResponse
from ...core.auth import AuthedUser, get_optional_user
from ...core.config import settings
from ...core.credentials import resolve_credential
from ...core.byok import byok_router_from_headers
from ...core.identity import resolve_identity, set_identity_cookie
from ...core.pii import PiiRedactionFailed, redact, reinject
from ...experiment.montecarlo import run_monte_carlo
from ...router.model_router import ModelRouter, router as default_router
from ..limiter import limiter

router = APIRouter()


def _require_csrf(x_fable_request: str = Header(default="")) -> None:
    if x_fable_request != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF header X-FABLE-Request: 1",
        )


async def _resolve_router(
    auth: AuthedUser | None,
    byok_key: str = "",
    byok_base_url: str = "",
    byok_provider: str = "",
) -> ModelRouter:
    session = byok_router_from_headers(byok_key, byok_base_url, byok_provider)
    if session is not None:
        return session
    if settings.use_supabase and auth:
        try:
            cred = await resolve_credential(auth.id)
            if cred:
                return ModelRouter(api_key=cred.api_key, base_url=cred.base_url)
        except Exception:
            pass
    return default_router


@router.post("/experiment/run", response_model=MonteCarloResponse)
@limiter.limit("5/minute")
async def experiment_run(
    req: MonteCarloRequest,
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
    _csrf: None = Depends(_require_csrf),
    x_byok_key: str = Header(default=""),
    x_byok_base_url: str = Header(default=""),
    x_byok_provider: str = Header(default=""),
) -> MonteCarloResponse:
    """Run a Monte Carlo prompt robustness experiment.

    Generates n_variants paraphrased prompts, sends each to multiple models in
    parallel, computes inter-model cosine similarity, returns consensus score
    and divergence pairs. Also feeds agreement signal back into the knowledge engine.
    """
    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    active_router = await _resolve_router(auth, x_byok_key, x_byok_base_url, x_byok_provider)

    # PII redaction — must run before any LLM call
    try:
        redaction = await redact(req.input, router=active_router)
    except PiiRedactionFailed as exc:
        raise HTTPException(
            500,
            detail={"error": "pii_redaction_failed", "reason": str(exc)},
        )

    try:
        result = await run_monte_carlo(
            prompt=redaction.redacted,
            n_variants=req.n_variants,
            models=req.models,
            router=active_router,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "experiment_failed", "reason": str(exc)},
        ) from exc

    # Reinject PII into variants and responses (user sees their own names)
    reinjected_variants = [reinject(v, redaction.entities) for v in result.variants]
    reinjected_responses = [
        [reinject(r, redaction.entities) for r in row]
        for row in result.responses
    ]

    return MonteCarloResponse(
        prompt=reinject(result.prompt, redaction.entities),
        variants=reinjected_variants,
        models=result.models,
        responses=reinjected_responses,
        similarity_matrix=result.similarity_matrix,
        consensus_score=result.consensus_score,
        divergence_pairs=result.divergence_pairs,
        per_model_consensus=result.per_model_consensus,
    )
