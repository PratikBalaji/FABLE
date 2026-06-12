"""
Minimal FastAPI service for agent pods in K8s mode.

Each pod runs this service with AGENT_ROLES env var set to a comma-separated
list of roles it handles (e.g. "adv:planner,adv:judge"). The coordinator
dispatches to this endpoint via HTTP.

Usage:
    AGENT_ROLES=adv:planner,adv:judge uvicorn backend.agents.agent_service:app --port 8001
"""
from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..core.bus import AgentBus
from ..core.serialization import (
    deserialize_task_context,
    serialize_agent_message,
)
from ..router.model_router import ModelRouter

log = structlog.get_logger()

app = FastAPI(title="F.A.B.L.E. Agent Pod")

# Local bus for this pod's agents only
_pod_bus = AgentBus()
_pod_router: ModelRouter | None = None

# Roles this pod serves (configured via AGENT_ROLES env var)
CONFIGURED_ROLES: list[str] = []


class InvokeRequest(BaseModel):
    role: str
    task_context: dict


class InvokeResponse(BaseModel):
    agent_message: dict


@app.on_event("startup")
async def _register_pod_agents() -> None:
    """Register only the agents this pod is configured to serve."""
    global CONFIGURED_ROLES, _pod_router

    roles_str = os.environ.get("AGENT_ROLES", "")
    if not roles_str:
        log.warning("agent_pod_no_roles", msg="AGENT_ROLES env var not set")
        return

    CONFIGURED_ROLES = [r.strip() for r in roles_str.split(",") if r.strip()]

    # Create a ModelRouter for this pod (reads API keys from env/config)
    _pod_router = ModelRouter()

    # Import and register adversarial agents
    from .adversarial import (
        ActorAgent,
        AdversarialCriticAgent,
        JudgeAgent,
        PlannerAgent,
        RefinerAgent,
        ValidatorAgent,
    )

    # Annotated as Any so mypy doesn't infer the abstract base type
    role_to_class: dict[str, Any] = {
        "adv:planner": PlannerAgent,
        "adv:actor": ActorAgent,
        "adv:critic": AdversarialCriticAgent,
        "adv:validator": ValidatorAgent,
        "adv:refiner": RefinerAgent,
        "adv:judge": JudgeAgent,
    }

    for role in CONFIGURED_ROLES:
        cls = role_to_class.get(role)
        if cls:
            agent = cls(_pod_router)
            _pod_bus.register(role, agent)
            log.info("agent_pod_registered", role=role)
        else:
            log.warning("agent_pod_unknown_role", role=role)

    log.info("agent_pod_ready", roles=CONFIGURED_ROLES)


@app.post("/agent/invoke", response_model=InvokeResponse)
async def invoke_agent(req: InvokeRequest) -> InvokeResponse:
    """Invoke an agent on this pod."""
    if req.role not in CONFIGURED_ROLES:
        raise HTTPException(
            status_code=404,
            detail=f"Role '{req.role}' not served by this pod. Available: {CONFIGURED_ROLES}",
        )

    # Deserialize TaskContext (each pod injects its own router)
    ctx = deserialize_task_context(req.task_context)
    ctx.metadata["router"] = _pod_router

    try:
        msg = await _pod_bus.dispatch(req.role, ctx)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No agent registered for role '{req.role}'")
    except Exception as exc:
        log.error("agent_pod_invoke_error", role=req.role, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return InvokeResponse(agent_message=serialize_agent_message(msg))


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "roles": CONFIGURED_ROLES,
        "pod_type": "agent",
    }
