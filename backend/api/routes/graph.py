from fastapi import APIRouter
from ..schemas import GraphState
from ...core.knowledge_engine import knowledge_engine

router = APIRouter()


@router.get("/graph", response_model=GraphState)
def get_graph() -> GraphState:
    return GraphState(**knowledge_engine.get_graph_state())


@router.get("/graph/models")
def get_model_performance(domain: str | None = None) -> dict:
    return knowledge_engine.get_model_performance(domain)
