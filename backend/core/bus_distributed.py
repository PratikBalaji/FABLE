"""
Distributed AgentBus — dispatches agent calls to remote K8s pods via HTTP.

Subclasses the in-process AgentBus. When a role maps to a known pod group,
the dispatch is routed over HTTP to that pod's /agent/invoke endpoint.
Non-adversarial roles (standard pipeline) fall back to local dispatch.

Pod grouping:
  - planning:  adv:planner, adv:judge   (strategic roles, Claude)
  - execution: adv:actor, adv:refiner   (content generation)
  - review:    adv:critic, adv:validator (adversarial review)
"""
from __future__ import annotations

import httpx
import structlog

from .bus import AgentBus, AgentMessage, TaskContext
from .serialization import (
    deserialize_agent_message,
    serialize_task_context,
)

log = structlog.get_logger()

# Maps each adversarial role to its pod group name
_ROLE_TO_GROUP: dict[str, str] = {
    "adv:planner": "planning",
    "adv:judge": "planning",
    "adv:actor": "execution",
    "adv:refiner": "execution",
    "adv:critic": "review",
    "adv:validator": "review",
}


class DistributedAgentBus(AgentBus):
    """
    AgentBus that dispatches adversarial roles to remote K8s agent pods.

    Non-adversarial roles (analyst, critic, synthesizer) are dispatched locally
    via the parent AgentBus.dispatch().
    """

    def __init__(self, service_registry: dict[str, str]) -> None:
        """
        Args:
            service_registry: maps pod group names to service URLs, e.g.:
                {
                    "planning": "http://planning-pod:8001",
                    "execution": "http://execution-pod:8002",
                    "review": "http://review-pod:8003",
                }
        """
        super().__init__()
        self._service_registry = service_registry
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def dispatch(self, role: str, ctx: TaskContext) -> AgentMessage:
        """
        Dispatch to the appropriate agent pod (remote) or local handler.

        Remote dispatch serializes TaskContext, POSTs to the pod, and
        deserializes the AgentMessage response. The message is appended
        to ctx.history (same contract as the local bus).
        """
        group = _ROLE_TO_GROUP.get(role)
        service_url = self._service_registry.get(group, "") if group else ""

        if service_url:
            return await self._remote_dispatch(role, ctx, service_url)

        # Fallback to local dispatch for non-adversarial roles
        return await super().dispatch(role, ctx)

    async def _remote_dispatch(
        self, role: str, ctx: TaskContext, service_url: str
    ) -> AgentMessage:
        """Send an agent invocation request to a remote pod."""
        url = f"{service_url}/agent/invoke"
        payload = {
            "role": role,
            "task_context": serialize_task_context(ctx),
        }

        log.info(
            "distributed_dispatch",
            role=role,
            task_id=ctx.task_id,
            target=service_url,
        )

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "distributed_dispatch_http_error",
                role=role,
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            raise
        except httpx.RequestError as exc:
            log.error(
                "distributed_dispatch_connection_error",
                role=role,
                target=service_url,
                error=str(exc),
            )
            raise

        data = resp.json()
        msg = deserialize_agent_message(data["agent_message"])
        ctx.history.append(msg)

        log.info(
            "distributed_dispatch_done",
            role=role,
            task_id=ctx.task_id,
            tokens=len(msg.content),
        )
        return msg

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
