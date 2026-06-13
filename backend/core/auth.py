"""
FastAPI auth dependency — verifies Supabase-issued JWTs.

Default path: asymmetric JWKS (ES256/RS256) fetched from
{SUPABASE_URL}/auth/v1/.well-known/jwks.json — no shared secret in the backend,
supports key rotation. Legacy HS256 (shared SUPABASE_JWT_SECRET) is available
behind USE_JWKS=false for older projects.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
import structlog
from fastapi import Header, HTTPException, status

from .config import settings

log = structlog.get_logger()

_ASYMMETRIC_ALGS = ["ES256", "RS256"]


@dataclass
class AuthedUser:
    id: str            # the JWT `sub` claim — used as user_id everywhere
    email: str | None
    token: str         # raw access token (for optional RLS-scoped calls)


_jwk_client: "jwt.PyJWKClient | None" = None


def _get_jwk_client() -> "jwt.PyJWKClient":
    global _jwk_client
    if _jwk_client is None:
        url = settings.resolved_jwks_url
        if not url:
            raise RuntimeError("JWKS URL not configured (set SUPABASE_URL or SUPABASE_JWKS_URL)")
        _jwk_client = jwt.PyJWKClient(url)  # caches keys internally
    return _jwk_client


def _decode(token: str) -> dict:
    if settings.use_jwks:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ASYMMETRIC_ALGS,
            audience=settings.jwt_audience,
            options={"verify_aud": True},
        )
    if not settings.supabase_jwt_secret:
        raise RuntimeError("SUPABASE_JWT_SECRET is required when USE_JWKS=false")
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
    )


async def get_current_user(authorization: str = Header(default="")) -> AuthedUser:
    """Verify the Bearer token and return the authenticated user."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = _decode(token)
    except Exception as exc:  # noqa: BLE001
        log.info("jwt_verification_failed", error=str(exc))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject claim")
    return AuthedUser(id=sub, email=claims.get("email"), token=token)


async def get_optional_user(authorization: str = Header(default="")) -> "AuthedUser | None":
    """Enforce auth only in multi-user mode; legacy single-user mode stays open."""
    if not settings.use_supabase:
        return None
    if settings.env == "local":
        # Local dev: bypass JWT so frontend can test without a Supabase session.
        # Production (ENV != "local") still enforces tokens.
        log.warning("auth_bypassed_local_dev")
        return AuthedUser(id="dev-local", email="dev@local", token="")
    return await get_current_user(authorization)
