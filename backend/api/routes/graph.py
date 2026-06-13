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


@router.get("/graph/elm")
def get_elm_status() -> dict:
    """Phase 11: ELM meta-scorer status for the frontend stats chip."""
    elm = knowledge_engine._elm
    return {
        "elm_trained": elm.is_trained,
        "elm_samples": elm.n_samples,
    }
