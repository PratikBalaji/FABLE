"""Agent Bus — routes tasks to registered agents and collects responses."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

import structlog

log = structlog.get_logger()


@dataclass
class AgentMessage:
    role: str                   # e.g. "analyst", "critic", "synthesizer"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TaskContext:
    task_id: str
    domain: str                 # "code_review" | "finance"
    input: str
    history: list[AgentMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


AgentHandler = Callable[[TaskContext], Coroutine[Any, Any, AgentMessage]]


class AgentBus:
    """Central message bus for multi-agent coordination."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentHandler] = {}
        self._middleware: list[Callable] = []

    def register(self, role: str, handler: AgentHandler) -> None:
        self._agents[role] = handler
        log.info("agent_registered", role=role)

    def use(self, middleware: Callable) -> None:
        self._middleware.append(middleware)

    async def dispatch(self, role: str, ctx: TaskContext) -> AgentMessage:
        if role not in self._agents:
            raise KeyError(f"No agent registered for role '{role}'")
        handler = self._agents[role]
        msg = await handler(ctx)
        ctx.history.append(msg)
        log.info("agent_dispatched", role=role, task_id=ctx.task_id, tokens=len(msg.content))
        return msg

    async def run_collaboration(
        self,
        ctx: TaskContext,
        pipeline: list[str],
    ) -> list[AgentMessage]:
        """Run a sequential pipeline of agent roles."""
        results: list[AgentMessage] = []
        for role in pipeline:
            msg = await self.dispatch(role, ctx)
            results.append(msg)
        return results


bus = AgentBus()
