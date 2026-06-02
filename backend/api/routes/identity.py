"""Identity routes (P4a).

GET    /identity/me           — return current identity (mints + sets cookie on first hit)
POST   /identity/link         — link pseudonymous id to Supabase auth user (needs JWT + consent)
DELETE /identity/me/memory    — hard-reset every memory artefact owned by this identity
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ...core.auth import AuthedUser, get_optional_user
from ...core.identity import (
    Identity,
    link_identity,
    reset_memory_for,
    resolve_identity,
    set_identity_cookie,
)

router = APIRouter()


def _to_dict(i: Identity) -> dict:
    return {
        "id": i.id,
        "pseudonymous": i.pseudonymous,
        "auth_user_id": i.auth_user_id,
        "linked_at": i.linked_at,
        "consent_link": i.consent_link,
        "consent_memory": i.consent_memory,
        "created_at": i.created_at,
        "last_seen_at": i.last_seen_at,
    }


@router.get("/identity/me")
async def get_me(
    request: Request,
    response: Response,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
) -> dict:
    ident = await resolve_identity(request, auth)
    if ident.cookie_to_set:
        set_identity_cookie(response, ident.cookie_to_set)
    return _to_dict(ident)


@router.post("/identity/link")
async def post_link(
    request: Request,
    response: Response,
    consent_link: bool = Body(..., embed=True),
    auth: AuthedUser = Depends(get_optional_user),
) -> dict:
    if auth is None:
        raise HTTPException(401, "Must be signed in via Supabase to link an identity")
    ident = await resolve_identity(request, None)  # use cookie, NOT auth (we want the pseudo id)
    try:
        linked = await link_identity(ident.id, auth.id, consent_link)
    except ValueError as e:
        raise HTTPException(400, str(e))
    set_identity_cookie(response, linked.id)
    return _to_dict(linked)


@router.delete("/identity/me/memory")
async def delete_memory(
    request: Request,
    auth: Optional[AuthedUser] = Depends(get_optional_user),
) -> dict:
    ident = await resolve_identity(request, auth)
    counts = await reset_memory_for(ident.id)
    return {"identity_id": ident.id, "deleted": counts}
