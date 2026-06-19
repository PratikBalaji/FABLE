"""POST /export/kaggle — push F.A.B.L.E. benchmark dataset + reproducer notebook to Kaggle."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.auth import AuthedUser, get_optional_user
from ..limiter import limiter

router = APIRouter()


class KaggleCredentials(BaseModel):
    username: str = Field(..., min_length=1, description="Kaggle username")
    key: str = Field(..., min_length=20, description="Kaggle API key")


class KaggleExportRequest(BaseModel):
    credentials: KaggleCredentials
    dataset_slug: str = Field(default="fable-benchmark-v1", pattern=r"^[a-z0-9\-]+$")


class KaggleExportResponse(BaseModel):
    dataset_url: str
    kernel_url: str


def _require_csrf(x_fable_request: str = Header(default="")) -> None:
    if x_fable_request != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF header X-FABLE-Request: 1",
        )


@limiter.limit("3/minute")
@router.post("/export/kaggle", response_model=KaggleExportResponse)
async def export_kaggle(
    req: KaggleExportRequest,
    request: Request,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
    _csrf: None = Depends(_require_csrf),
) -> KaggleExportResponse:
    """Build the 60-case benchmark dataset + reproducer notebook and push to Kaggle.

    Accepts Kaggle credentials (username + key) per-request — never stored
    in logs or persisted in plaintext. Handles exactly like the OpenRouter
    BYOK key: credentials are used only for this request, then discarded.
    """
    try:
        from ...evaluation.export_kaggle import build_and_push
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "export_unavailable", "reason": str(exc)},
        )

    # Redact credentials from structured logs
    import structlog
    log = structlog.get_logger()
    log.info("kaggle_export_requested",
             user=auth.id if auth else "anon",
             slug=req.dataset_slug)

    try:
        urls = await build_and_push(
            kaggle_creds={
                "username": req.credentials.username,
                "key": req.credentials.key,  # used in-process only, never logged
            },
            dataset_slug=req.dataset_slug,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "benchmark_not_found", "reason": str(exc)},
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "kaggle_push_failed", "reason": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        log.error("kaggle_export_error", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={"error": "export_failed", "reason": str(exc)},
        )

    return KaggleExportResponse(**urls)
