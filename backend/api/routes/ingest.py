import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form, status

from ..schemas import IngestRequest, IngestResponse
from ...core.auth import get_optional_user, AuthedUser
from ...core.config import settings
from ...core.identity import resolve_identity, set_identity_cookie
from ...rag.pipeline import vector_store

log = structlog.get_logger()

router = APIRouter()

# F-024: max upload size 10 MB
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "text/csv",
    "application/json",
}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    req: IngestRequest,
    request: Request,
    response: Response,
    auth: AuthedUser | None = Depends(get_optional_user),
) -> IngestResponse:
    identity_id: str | None = None
    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    n = vector_store.ingest(req.text, metadata={"source": req.source, "identity_id": identity_id})
    return IngestResponse(chunks_added=n, source=req.source)


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    source: str = Form("upload"),
    auth: AuthedUser | None = Depends(get_optional_user),
) -> IngestResponse:
    # F-024: content-type allowlist
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {ct}",
        )

    # F-024: size limit
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_UPLOAD_BYTES // (1024*1024)} MB limit",
        )

    identity_id: str | None = None
    if settings.use_supabase:
        ident = await resolve_identity(request, auth)
        identity_id = ident.id
        if ident.cookie_to_set:
            set_identity_cookie(response, ident.cookie_to_set)

    from ...rag.extract import extract as extract_doc
    try:
        text = extract_doc(content, file.filename or "upload")
    except (ValueError, ImportError) as exc:
        # Fall back to raw UTF-8 decode for unsupported types (e.g. plain .log)
        log.warning("extract_fallback", reason=str(exc), filename=file.filename)
        text = content.decode("utf-8", errors="ignore")
    n = vector_store.ingest(
        text,
        metadata={"source": source or file.filename or "upload", "identity_id": identity_id},
    )
    return IngestResponse(chunks_added=n, source=source)
