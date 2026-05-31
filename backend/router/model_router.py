"""
Learned Model Router — routes queries to the best-performing model
based on historical performance data from the knowledge engine.

Starts with 2 models, learns which excels at what over time.
"""
from __future__ import annotations

from dataclasses import dataclass

import openai
import structlog

from ..core.config import settings

log = structlog.get_logger()


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: dict[str, int]


# Available models on OpenRouter
AVAILABLE_MODELS = {
    "primary": settings.primary_model,       # Claude Sonnet
    "secondary": settings.secondary_model,   # GPT-4o-mini
}


class ModelRouter:
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.app_url,
                "X-Title": settings.app_name,
            },
        )

    async def complete(
        self,
        system: str,
        user: str,
        role_hint: str = "",
        force_model: str | None = None,
    ) -> ModelResponse:
        model = force_model or settings.primary_model

        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=2048,
        )
        msg = resp.choices[0].message
        return ModelResponse(
            content=msg.content or "",
            model=resp.model,
            usage={
                "input": resp.usage.prompt_tokens if resp.usage else 0,
                "output": resp.usage.completion_tokens if resp.usage else 0,
            },
        )

    async def complete_with_routing(
        self,
        system: str,
        user: str,
        role_hint: str = "",
        preferred_model: str | None = None,
    ) -> ModelResponse:
        """
        Route to a model based on learned performance data.
        preferred_model comes from the knowledge engine's recommendation.
        Falls back to primary model if no recommendation exists.
        """
        model = preferred_model or settings.primary_model
        log.info("model_routed", model=model, role=role_hint, learned=preferred_model is not None)
        return await self.complete(system, user, role_hint, force_model=model)

    async def compare_models(
        self,
        system: str,
        user: str,
    ) -> dict[str, ModelResponse]:
        """Run the same prompt through both models for comparison."""
        import asyncio
        results = {}
        tasks = []
        for label, model_id in AVAILABLE_MODELS.items():
            tasks.append(self._run_model(label, model_id, system, user))
        completed = await asyncio.gather(*tasks)
        for label, response in completed:
            results[label] = response
        return results

    async def _run_model(
        self, label: str, model_id: str, system: str, user: str
    ) -> tuple[str, ModelResponse]:
        response = await self.complete(system, user, force_model=model_id)
        return (label, response)


router = ModelRouter()
