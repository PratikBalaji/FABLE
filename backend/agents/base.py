"""Base agent class with prompt templating and model call abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.bus import AgentMessage, TaskContext
from ..router.model_router import ModelRouter


class BaseAgent(ABC):
    role: str = "base"
    system_prompt: str = "You are a helpful AI agent."

    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    @abstractmethod
    def build_prompt(self, ctx: TaskContext) -> str:
        """Construct the user-turn prompt from task context."""

    async def __call__(self, ctx: TaskContext) -> AgentMessage:
        prompt = self.build_prompt(ctx)
        response = await self.router.complete(
            system=self.system_prompt,
            user=prompt,
            role_hint=self.role,
        )
        return AgentMessage(
            role=self.role,
            content=response.content,
            metadata={"model": response.model, "usage": response.usage},
        )
