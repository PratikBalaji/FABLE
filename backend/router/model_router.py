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
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        # BYOK (F-015): per-user credential override; falls back to server global key.
        self._client = openai.AsyncOpenAI(
            api_key=api_key or settings.openrouter_api_key,
            base_url=base_url or settings.openrouter_base_url,
            timeout=45.0,   # P14: fail a hung upstream call fast → fallback chain handles it
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
        fallback_chain = [model, settings.secondary_model]
        seen: set[str] = set()
        last_exc: Exception | None = None
        for candidate in fallback_chain:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return await self._call_model(candidate, system, user, max_tokens=2048)
            except openai.BadRequestError as exc:
                log.warning("complete_bad_request", model=candidate, role=role_hint, error=str(exc))
                last_exc = exc
            except openai.NotFoundError as exc:
                log.warning("complete_model_not_found", model=candidate, role=role_hint, error=str(exc))
                last_exc = exc
        raise RuntimeError(
            f"All models failed for role '{role_hint}'. Last error: {last_exc}"
        ) from last_exc

    async def _call_model(self, model: str, system: str, user: str, max_tokens: int) -> ModelResponse:
        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
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

    async def complete_for_role(
        self,
        role: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        model_override: str | None = None,
    ) -> ModelResponse:
        # ELM-provided model_override takes precedence over static map
        if model_override:
            model = model_override
        else:
            model_map = {
                "adv:planner": settings.planner_model,
                "adv:actor": settings.actor_model,
                "adv:critic": settings.adv_critic_model,
                "adv:validator": settings.validator_model,
                "adv:refiner": settings.refiner_model,
                "adv:judge": settings.judge_model,
            }
            model = model_map.get(role, settings.primary_model)

        fallback_chain = [model, settings.primary_model, settings.secondary_model]
        seen: set[str] = set()
        last_exc: Exception | None = None
        for candidate in fallback_chain:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return await self._call_model(candidate, system, user, max_tokens)
            except openai.BadRequestError as exc:
                log.warning("model_bad_request", model=candidate, role=role, error=str(exc))
                last_exc = exc
            except openai.NotFoundError as exc:
                log.warning("model_not_found", model=candidate, role=role, error=str(exc))
                last_exc = exc
        raise RuntimeError(
            f"All models failed for role '{role}'. Last error: {last_exc}"
        ) from last_exc


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
