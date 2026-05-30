from fastapi import APIRouter, UploadFile, File, Form
from ..schemas import IngestRequest, IngestResponse
from ...rag.pipeline import vector_store

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(req: IngestRequest) -> IngestResponse:
    n = vector_store.ingest(req.text, metadata={"source": req.source})
    return IngestResponse(chunks_added=n, source=req.source)


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(file: UploadFile = File(...), source: str = Form("upload")) -> IngestResponse:
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    n = vector_store.ingest(text, metadata={"source": source or file.filename or "upload"})
    return IngestResponse(chunks_added=n, source=source)
