"""FastAPI application entry point."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..agents.register import register_all
from ..agents.adversarial_register import register_adversarial
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
    title="F.A.B.L.E. API",
    description="Federated Agent Bus & Lifecycle Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(run.router, tags=["Orchestration"])
app.include_router(feedback.router, tags=["Feedback"])
app.include_router(ingest.router, tags=["RAG"])
app.include_router(graph.router, tags=["Knowledge Graph"])
app.include_router(identity.router, tags=["Identity"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
