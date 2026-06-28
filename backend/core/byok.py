"""Session BYOK — build a per-request ModelRouter from request headers.

No storage, no auth, no logging of the key. The key lives only in the caller's
browser (localStorage) and is sent per-request via headers. This lets anonymous
Vercel visitors run the app with their own provider quota.

Headers:
    X-BYOK-Key        — the provider API key (required to activate)
    X-BYOK-Base-URL   — optional OpenAI-compatible base URL override
    X-BYOK-Provider   — optional provider name (openrouter/openai/anthropic/google)
                        used only to pick a default base_url when none supplied.
"""
from __future__ import annotations

from .credentials import PROVIDER_BASE_URLS
from ..router.model_router import ModelRouter


def byok_router_from_headers(
    x_byok_key: str = "",
    x_byok_base_url: str = "",
    x_byok_provider: str = "",
) -> ModelRouter | None:
    """Return a per-request ModelRouter if a session BYOK key is present, else None.

    Never logs the key. base_url resolution order:
    explicit header → provider default map → None (ModelRouter falls back to OpenRouter).
    """
    key = (x_byok_key or "").strip()
    if not key:
        return None

    base_url = (x_byok_base_url or "").strip()
    if not base_url:
        provider = (x_byok_provider or "").strip().lower()
        base_url = PROVIDER_BASE_URLS.get(provider, "") or None  # type: ignore[assignment]

    return ModelRouter(api_key=key, base_url=base_url or None)
