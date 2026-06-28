"""Runtime config endpoints (Phase 15):

- GET  /config/pii   — current PII redaction mode + Presidio reachability.
- POST /config/pii   — live-switch PII mode (regex_llm ↔ presidio sidecar).
- POST /byok/test    — validate a session BYOK key (no auth, no storage).
"""
from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.config import settings
from ...core.credentials import validate_key
from ...core.pii import effective_presidio_url, set_presidio_override, redact
from ...router.model_router import router as default_router
from ..limiter import limiter

log = structlog.get_logger()
router = APIRouter()


def _require_csrf(x_fable_request: str) -> None:
    if x_fable_request != "1":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Missing CSRF header X-FABLE-Request: 1")


async def _presidio_reachable(url: str) -> bool:
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(f"{url.rstrip('/')}/health")
            return resp.status_code < 500
    except Exception:
        return False


@router.get("/config/limits")
async def get_rate_limits() -> dict:
    """Phase 19: expose configured rate limits + per-identity concurrency so the
    dashboard can show quota. Live remaining counts come from X-RateLimit-* response
    headers on each rate-limited call, not from this endpoint."""
    return {
        "global": settings.rate_limit_global,
        "run": settings.rate_limit_run,
        "adversarial": settings.rate_limit_adv,
        "max_concurrent_per_identity": settings.max_concurrent_per_identity,
    }


@router.get("/config/pii")
async def get_pii_config() -> dict:
    url = effective_presidio_url()
    return {
        "pii_enabled": settings.pii_enabled,
        "mode": "presidio" if url else "regex_llm",
        "presidio_url": url,
        "presidio_reachable": await _presidio_reachable(url),
        "pii_llm_fallback": settings.pii_llm_fallback,
    }


class PiiModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(presidio|regex_llm)$")
    presidio_url: str = Field(default="http://localhost:3000")


@router.post("/config/pii")
@limiter.limit("10/minute")
async def set_pii_config(
    body: PiiModeRequest,
    request: Request,
    x_fable_request: str = Header(default=""),
) -> dict:
    _require_csrf(x_fable_request)

    if body.mode == "regex_llm":
        set_presidio_override(None)
        return {"ok": True, "mode": "regex_llm"}

    # presidio: require a reachable sidecar before flipping
    url = body.presidio_url.strip().rstrip("/")
    if not await _presidio_reachable(url):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "presidio_unreachable",
                "reason": (
                    f"No Presidio sidecar reachable at {url}. This requires a "
                    "self-hosted backend that can reach the container. Run: "
                    "docker run -p 3000:3000 mcr.microsoft.com/presidio-analyzer:latest"
                ),
            },
        )
    set_presidio_override(url)
    log.info("pii_mode_switched", mode="presidio", url=url)
    return {"ok": True, "mode": "presidio", "presidio_url": url}


class RedactPreviewRequest(BaseModel):
    text: str = Field(..., max_length=4000)


@router.post("/config/pii/preview")
@limiter.limit("30/minute")
async def redact_preview(
    body: RedactPreviewRequest,
    request: Request,
    x_byok_key: str = Header(default=""),
    x_byok_base_url: str = Header(default=""),
    x_byok_provider: str = Header(default=""),
    x_fable_request: str = Header(default=""),
) -> dict:
    """Live PII-redaction preview: returns redacted text + detected entity spans.

    Echoes the caller's own text back (that is the point of a preview), so it is
    rate-limited and capped at 4000 chars. Uses the active PII mode (regex+LLM or
    the Presidio override). LLM layer uses a session BYOK key if provided.
    """
    _require_csrf(x_fable_request)
    # session BYOK key powers the LLM extraction layer (when in regex+LLM mode)
    from ...core.byok import byok_router_from_headers
    router_for_llm = byok_router_from_headers(x_byok_key, x_byok_base_url, x_byok_provider) or default_router
    result = await redact(body.text, router=router_for_llm)
    return {
        "original": body.text,
        "redacted": result.redacted,
        "mode": "presidio" if effective_presidio_url() else "regex_llm",
        "entities": [
            {
                "type": e.entity_type,
                "placeholder": e.placeholder,
                "value": e.entity_value,
                "start": e.start,
                "end": e.end,
                "score": round(e.score, 2),
            }
            for e in result.entities
        ],
    }


class ByokTestRequest(BaseModel):
    provider: str = Field(default="openrouter")
    api_key: str = Field(..., min_length=8)
    base_url: str | None = None


@router.post("/byok/test")
@limiter.limit("10/minute")
async def test_byok_key(
    body: ByokTestRequest,
    request: Request,
    x_fable_request: str = Header(default=""),
) -> dict:
    """Validate a session BYOK key against the provider. No auth, never stored, never logged."""
    _require_csrf(x_fable_request)
    ok, detail = await validate_key(body.provider, body.api_key, body.base_url)
    return {"ok": ok, "detail": detail}
