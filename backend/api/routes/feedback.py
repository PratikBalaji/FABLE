from fastapi import APIRouter, Query
from ...core.knowledge_engine import knowledge_engine

router = APIRouter()


@router.get("/feedback/stats")
def feedback_stats(domain: str | None = Query(None)) -> dict:
    perf = knowledge_engine.get_model_performance(domain)
    graph = knowledge_engine.get_graph_state()
    return {
        "total_runs": graph["stats"]["totalRuns"],
        "model_performance": perf,
        "domain": domain,
    }
