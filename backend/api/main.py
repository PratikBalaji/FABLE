"""FastAPI application entry point."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from ..agents.register import register_all
from ..agents.adversarial_register import register_adversarial
from ..core.config import settings
from .limiter import limiter
from .routes import run, feedback, ingest, graph, identity

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all()
    register_adversarial()
    log.info("fable_started")
    yield
    log.info("fable_stopped")


app = FastAPI(
    title="FABLE API",
    description="Framework for Adversarial Benchmarking and Logic Evaluation",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# F-008/F-009: restrict CORS to trusted origins with credentials.
# Set CORS_ORIGINS env var in production (e.g. "https://app.vercel.app").
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.trusted_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-FABLE-Request"],
)

app.include_router(run.router, tags=["Orchestration"])
app.include_router(feedback.router, tags=["Feedback"])
app.include_router(ingest.router, tags=["RAG"])
app.include_router(graph.router, tags=["Knowledge Graph"])
app.include_router(identity.router, tags=["Identity"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
