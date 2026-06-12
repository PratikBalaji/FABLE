"""
Pseudonymous-first identity for F.A.B.L.E.

Identity resolution order (P4a):
  1. Supabase JWT in Authorization: Bearer → look up identity by auth_user_id;
     mint a non-pseudonymous identity row if first time.
  2. Signed cookie `fable_id` → look up identity by uuid.
  3. None of the above → mint a fresh pseudonymous identity and set the cookie.

A pseudonymous identity can later be linked to a Supabase auth user via
`POST /identity/link` (requires JWT + explicit consent_link=true).

Cookie format: itsdangerous URLSafeTimedSerializer(secret).dumps(identity_uuid).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast

import structlog
from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .auth import AuthedUser
from .config import settings
from .db import get_db

log = structlog.get_logger()


@dataclass
class Identity:
    id: str
    pseudonymous: bool
    auth_user_id: str | None = None
    linked_at: str | None = None
    consent_link: bool = False
    consent_memory: bool = True
    created_at: str | None = None
    last_seen_at: str | None = None
    cookie_to_set: str | None = None  # if set, route handler should call set_cookie


# --- cookie helpers --------------------------------------------------------

def _serializer() -> URLSafeTimedSerializer:
    secret = settings.identity_cookie_secret
    if not secret:
        raise RuntimeError(
            "IDENTITY_COOKIE_SECRET not set. Generate one: "
            'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
    return URLSafeTimedSerializer(secret, salt="fable-identity")


def _sign_cookie(identity_id: str) -> str:
    return _serializer().dumps(identity_id)


def _read_cookie(value: str) -> str | None:
    """Return identity_id if cookie is valid + unexpired, else None."""
    try:
        max_age = settings.identity_cookie_max_age_days * 86400
        return _serializer().loads(value, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def set_identity_cookie(response: Response, identity_id: str) -> None:
    """Helper for route handlers: stamp the signed cookie on the response.

    P6c: `samesite` + `secure` now read from settings to support cross-origin
    deploy (Vercel frontend ↔ Cloud Run backend → samesite="none", secure=true).
    Local dev (same-origin) keeps samesite="lax". Note: `none` requires HTTPS.
    """

    _samesite = (settings.cookie_samesite or "lax").lower()
    if _samesite not in ("lax", "strict", "none"):
        _samesite = "lax"
    samesite_value = cast(Literal["lax", "strict", "none"], _samesite)
    response.set_cookie(
        key=settings.identity_cookie_name,
        value=_sign_cookie(identity_id),
        max_age=settings.identity_cookie_max_age_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=cast(Literal["lax", "strict", "none"], samesite_value),
    )


# --- DB ops ----------------------------------------------------------------

def _row_to_identity(row: dict, cookie_to_set: str | None = None) -> Identity:
    return Identity(
        id=row["id"],
        pseudonymous=row["pseudonymous"],
        auth_user_id=row.get("auth_user_id"),
        linked_at=row.get("linked_at"),
        consent_link=row.get("consent_link", False),
        consent_memory=row.get("consent_memory", True),
        created_at=row.get("created_at"),
        last_seen_at=row.get("last_seen_at"),
        cookie_to_set=cookie_to_set,
    )


def _touch_last_seen(identity_id: str) -> None:
    try:
        get_db().table("identities").update(
            {"last_seen_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", identity_id).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("identity_touch_failed", id=identity_id, err=str(exc))


def _find_by_auth(auth_user_id: str) -> dict | None:
    rows = (
        get_db()
        .table("identities")
        .select("*")
        .eq("auth_user_id", auth_user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _find_by_id(identity_id: str) -> dict | None:
    rows = (
        get_db()
        .table("identities")
        .select("*")
        .eq("id", identity_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _mint(pseudonymous: bool = True, auth_user_id: str | None = None) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "pseudonymous": pseudonymous,
        "auth_user_id": auth_user_id,
        "consent_link": bool(auth_user_id),
        "consent_memory": True,
    }
    res = get_db().table("identities").insert(row).execute()
    return res.data[0]


# --- public API ------------------------------------------------------------

async def resolve_identity(
    request: Request, auth: AuthedUser | None = None
) -> Identity:
    """Return the Identity for this request, minting one if necessary.

    If a cookie needs to be set on the response, the returned Identity carries it
    in `.cookie_to_set` — the route handler must call `set_identity_cookie()`.
    """
    # 1. Authed path: look up / mint a non-pseudonymous identity tied to auth_user_id.
    if auth is not None:
        existing = _find_by_auth(auth.id)
        if existing:
            _touch_last_seen(existing["id"])
            return _row_to_identity(existing)
        row = _mint(pseudonymous=False, auth_user_id=auth.id)
        # also set cookie so subsequent unauthed requests still resolve
        return _row_to_identity(row, cookie_to_set=row["id"])

    # 2. Cookie path
    cookie = request.cookies.get(settings.identity_cookie_name)
    if cookie:
        identity_id = _read_cookie(cookie)
        if identity_id:
            found = _find_by_id(identity_id)
            if found:
                _touch_last_seen(found["id"])
                return _row_to_identity(found)
            # cookie referenced a missing row (cascade-deleted) → mint fresh
        # bad / expired signature → mint fresh

    # 3. Mint fresh pseudonymous identity
    row = _mint(pseudonymous=True)
    return _row_to_identity(row, cookie_to_set=row["id"])


async def link_identity(
    pseudo_id: str, auth_user_id: str, consent_link: bool
) -> Identity:
    """Bind a pseudonymous identity to a Supabase auth user.

    Requires explicit consent_link=true (notebook: "Explicit Consent for Linking").
    Refuses if the auth user already has a different linked identity (returns existing).
    """
    if not consent_link:
        raise ValueError("consent_link must be true to link a pseudonymous identity")

    db = get_db()
    existing = _find_by_auth(auth_user_id)
    if existing:
        log.info("identity_link_already_linked", auth_user_id=auth_user_id, existing=existing["id"])
        return _row_to_identity(existing)

    pseudo = _find_by_id(pseudo_id)
    if not pseudo:
        raise ValueError(f"pseudonymous identity {pseudo_id} not found")

    res = (
        db.table("identities")
        .update(
            {
                "auth_user_id": auth_user_id,
                "linked_at": datetime.now(timezone.utc).isoformat(),
                "consent_link": True,
                "pseudonymous": False,
            }
        )
        .eq("id", pseudo_id)
        .execute()
    )
    return _row_to_identity(res.data[0])


async def reset_memory_for(identity_id: str) -> dict[str, int]:
    """Hard-delete every memory artefact owned by this identity. Returns row counts."""
    db = get_db()
    counts: dict[str, int] = {}
    for table in (
        "memory_chunks",
        "chat_messages",
        "adversarial_messages",
        "adversarial_runs",
        "claims",            # may not exist yet (P4c); guarded below
        "contradictions",    # same
        "audit_log",         # same
        "chat_sessions",
        "pii_entity_map",    # via session cascade, but explicit purge OK
    ):
        try:
            res = (
                db.table(table)
                .delete()
                .eq("identity_id", identity_id)
                .execute()
            )
            counts[table] = len(res.data or [])
        except Exception as exc:  # noqa: BLE001
            counts[table] = -1  # signal "table missing / not yet created"
            log.warning("memory_reset_table_skipped", table=table, err=str(exc)[:80])
    return counts
