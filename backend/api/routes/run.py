from fastapi import APIRouter
from ..schemas import RunRequest, RunResponse, AgentMessageOut, GraphState
from ...core.lifecycle import run_task

router = APIRouter()


@router.post("/run", response_model=RunResponse)
async def run_collaboration(req: RunRequest) -> RunResponse:
    result = await run_task(
        input_text=req.input,
        domain=req.domain,
        pipeline=req.pipeline,
    )
    return RunResponse(
        task_id=result["task_id"],
        domain=result["domain"],
        pipeline=result["pipeline"],
        messages=[AgentMessageOut(**m) for m in result["messages"]],
        scores=result.get("scores", {}),
        model_used=result.get("model_used", ""),
        knowledge_graph=GraphState(**result["knowledge_graph"]),
    )
