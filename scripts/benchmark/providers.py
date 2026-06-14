"""
Benchmark provider factory + rate-limit-aware throttle.

Builds a dedicated ModelRouter pointed at a free OpenAI-compatible endpoint (Groq by default)
WITHOUT touching the user's main .env, and wraps it so every `complete()` call respects a
requests-per-minute budget and backs off on 429 / rate-limit errors. The wrapped router is
passed to run_task / run_adversarial_task via their existing `router=` parameter.
"""
from __future__ import annotations

import asyncio
import os
import random
import time

from backend.router.model_router import ModelRouter, ModelResponse

_PROVIDERS = {
    "groq":       ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "hf":         ("HF_TOKEN", "https://router.huggingface.co/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
}

# Sensible single-model defaults per provider (overridable via --model).
DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "hf": "meta-llama/Llama-3.3-70B-Instruct",
    "openrouter": "google/gemini-2.0-flash-001",
}
# Smaller model for the heterogeneous-roles ablation.
SMALL_MODELS = {
    "groq": "llama-3.1-8b-instant",
    "hf": "meta-llama/Llama-3.1-8B-Instruct",
    "openrouter": "google/gemini-flash-1.5-8b",
}


def _is_rate_limit(exc: Exception) -> bool:
    s = str(exc).lower()
    return "429" in s or "rate limit" in s or "too many requests" in s or "quota" in s


class ThrottledRouter(ModelRouter):
    """ModelRouter that enforces a global RPM budget and retries on rate-limit errors.

    Forces a single model for every role (force_model on complete; role map overridden) so the
    whole pipeline runs on one free-tier model unless `small_model` is set for hetero ablation.
    """

    def __init__(self, api_key: str, base_url: str, model: str,
                 rpm: int = 25, max_retries: int = 6, small_model: str | None = None):
        super().__init__(api_key=api_key, base_url=base_url)
        self._model = model
        self._small = small_model
        self._min_interval = 60.0 / max(1, rpm)
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self._max_retries = max_retries

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    def _model_for(self, role_hint: str, force_model: str | None) -> str:
        # Hetero ablation: Critic/Refiner roles use the small model.
        if self._small and role_hint in ("adv:critic", "adv:refiner", "critic"):
            return self._small
        return force_model or self._model

    async def complete(self, system: str, user: str, role_hint: str = "",
                       force_model: str | None = None) -> ModelResponse:
        model = self._model_for(role_hint, force_model)
        attempt = 0
        while True:
            await self._throttle()
            try:
                return await super().complete(system=system, user=user,
                                              role_hint=role_hint, force_model=model)
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                if not _is_rate_limit(exc) or attempt > self._max_retries:
                    raise
                # exponential backoff with jitter
                delay = min(60.0, (2 ** attempt) + random.uniform(0, 1.5))
                await asyncio.sleep(delay)

    async def complete_for_role(self, role: str, system: str, user: str,
                                max_tokens: int = 1024, model_override: str | None = None) -> ModelResponse:
        # Route every role through the throttled single-model complete().
        return await self.complete(system=system, user=user, role_hint=role,
                                   force_model=self._model_for(role, model_override))


def build_router(provider: str, model: str | None = None, rpm: int = 25,
                 hetero: bool = False) -> ThrottledRouter:
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; choose from {list(_PROVIDERS)}")
    env_key, base_url = _PROVIDERS[provider]
    api_key = os.environ.get(env_key)
    if not api_key:
        raise RuntimeError(f"{env_key} not set — needed for --provider {provider}")
    return ThrottledRouter(
        api_key=api_key,
        base_url=base_url,
        model=model or DEFAULT_MODELS[provider],
        rpm=rpm,
        small_model=SMALL_MODELS[provider] if hetero else None,
    )
