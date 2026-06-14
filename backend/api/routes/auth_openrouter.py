"""OpenRouter OAuth (PKCE) — lets a user authorize F.A.B.L.E. with their own OpenRouter account.

Flow:
  1. GET /auth/openrouter/start  -> generate PKCE verifier/challenge, store state, return auth URL
  2. user consents on openrouter.ai, which redirects to the callback with ?code&state
  3. GET /auth/openrouter/callback -> exchange code+verifier for a user-scoped key, store encrypted
"""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from ..schemas import OAuthStartOut
from ...core.auth import AuthedUser, get_current_user
from ...core.config import settings
from ...core.crypto import encrypt
from ...core.db import get_db

router = APIRouter()
log = structlog.get_logger()


def _gen_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


@router.get("/auth/openrouter/start", response_model=OAuthStartOut)
async def start(user: AuthedUser = Depends(get_current_user)) -> OAuthStartOut:
    verifier, challenge = _gen_pkce()
    db = get_db()
    res = (
        db.table("oauth_states")
        .insert(
            {
                "user_id": user.id,
                "provider": "openrouter",
                "code_verifier": verifier,
                "code_challenge": challenge,
            }
        )
        .execute()
    )
    state = str(res.data[0]["state"])
    params = {
        "callback_url": settings.openrouter_oauth_callback,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return OAuthStartOut(auth_url=f"{settings.openrouter_auth_url}?{urlencode(params)}", state=state)


@router.get("/auth/openrouter/callback")
async def callback(code: str, state: str):
    db = get_db()
    rows = db.table("oauth_states").select("*").eq("state", state).limit(1).execute().data or []
    if not rows:
        raise HTTPException(400, "Invalid or unknown OAuth state")
    st = rows[0]

    # Expiry check (defense-in-depth; states are short-lived).
    # F-003: fail CLOSED — if expires_at is missing or unparseable, reject the state
    # rather than silently proceeding (prevents indefinitely-valid OAuth states).
    raw_exp = st.get("expires_at")
    if not raw_exp:
        db.table("oauth_states").delete().eq("state", state).execute()
        raise HTTPException(400, "OAuth state has no expiry; please reconnect")
    try:
        expires_at = datetime.fromisoformat(raw_exp)
    except (TypeError, ValueError):
        db.table("oauth_states").delete().eq("state", state).execute()
        raise HTTPException(400, "OAuth state expiry is malformed; please reconnect")
    if expires_at < datetime.now(timezone.utc):
        db.table("oauth_states").delete().eq("state", state).execute()
        raise HTTPException(400, "OAuth state expired; please reconnect")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            settings.openrouter_key_exchange_url,
            json={
                "code": code,
                "code_verifier": st["code_verifier"],
                "code_challenge_method": "S256",
            },
        )
    if resp.status_code != 200:
        log.info("openrouter_key_exchange_failed", status=resp.status_code)
        raise HTTPException(400, "OpenRouter key exchange failed")

    key = resp.json().get("key")
    if not key:
        raise HTTPException(400, "OpenRouter returned no key")

    db.table("provider_connections").insert(
        {
            "user_id": st["user_id"],
            "provider": "openrouter",
            "conn_type": "oauth",
            "label": "OpenRouter (OAuth)",
            "secret_enc": encrypt(key, aad=st["user_id"].encode()),
            "last4": key[-4:],
            "status": "active",
            "last_validated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()
    db.table("oauth_states").delete().eq("state", state).execute()

    return RedirectResponse(url=f"{settings.app_url}/settings/providers?connected=openrouter")
