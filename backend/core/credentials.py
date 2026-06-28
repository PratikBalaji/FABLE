"""
Provider credential resolution + validation.

Base URLs point at each provider's OpenAI-COMPATIBLE endpoint so the existing
OpenAI-SDK-based ModelRouter works uniformly across providers. OpenRouter remains
the only path with full per-role multi-vendor routing; direct BYOK keys use a
single provider-default model (documented limitation).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from .config import settings
from .crypto import decrypt
from .db import get_db

log = structlog.get_logger()

# OpenAI-compatible endpoints per provider
PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",                       # OpenAI-compat path
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}

# Default model for direct BYOK keys (per-role routing is OpenRouter-only)
PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "openrouter": settings.primary_model,
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-1.5-flash",
}


@dataclass
class ResolvedCredential:
    provider: str
    api_key: str       # decrypted, in-memory only — never logged or returned
    base_url: str
    via: str           # 'oauth' | 'byok'


async def resolve_credential(
    user_id: str, preferred: str | None = None
) -> ResolvedCredential | None:
    """
    Pick the user's active credential. If `preferred` provider is given, use it;
    otherwise fall back to profile.default_provider, else the most recent active one.
    """
    db = get_db()

    if not preferred:
        prof = (
            db.table("profiles").select("default_provider").eq("id", user_id).limit(1).execute()
        )
        if prof.data and prof.data[0].get("default_provider"):
            preferred = prof.data[0]["default_provider"]

    q = (
        db.table("provider_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
    )
    if preferred:
        q = q.eq("provider", preferred)
    rows = q.order("created_at", desc=True).limit(1).execute().data or []

    # If a preferred provider had no connection, fall back to any active one.
    if not rows and preferred:
        rows = (
            db.table("provider_connections")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
    if not rows:
        return None

    row = rows[0]
    provider = row["provider"]
    base_url = row.get("base_url") or PROVIDER_BASE_URLS.get(provider, settings.openrouter_base_url)
    # F-014: decrypt with user_id as AAD — v2 ciphertext is bound to this row's owner.
    aad = row.get("user_id", "").encode() if row.get("user_id") else None
    return ResolvedCredential(
        provider=provider,
        api_key=decrypt(row["secret_enc"], aad=aad),
        base_url=base_url,
        via=row["conn_type"],
    )


async def validate_key(
    provider: str, api_key: str, base_url: str | None = None
) -> tuple[bool, str]:
    """Make a cheap authenticated request to confirm the key works before storing it."""
    base = (base_url or PROVIDER_BASE_URLS.get(provider, "")).rstrip("/")
    if not base:
        return False, f"unknown provider: {provider}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "anthropic":
                # Native Anthropic auth header
                resp = await client.get(
                    f"{base}/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
            elif provider == "google":
                resp = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {api_key}"})
            elif provider == "openrouter":
                # OpenRouter's /models is PUBLIC (200 for any key) → use the
                # auth-required /key endpoint so a bogus key is correctly rejected.
                resp = await client.get(f"{base}/key", headers={"Authorization": f"Bearer {api_key}"})
            else:  # openai
                resp = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {api_key}"})
    except Exception as exc:  # noqa: BLE001
        return False, f"request failed: {exc}"

    if resp.status_code == 200:
        return True, "ok"
    if resp.status_code in (401, 403):
        return False, "authentication failed (invalid key)"
    return False, f"unexpected status {resp.status_code}"
