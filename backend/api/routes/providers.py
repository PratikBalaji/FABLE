"""BYOK provider credential management. All endpoints require an authenticated user."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import ProviderAddRequest, ProviderConnectionOut, ProviderTestOut
from ...core.auth import AuthedUser, get_current_user
from ...core.credentials import PROVIDER_BASE_URLS, validate_key
from ...core.crypto import decrypt, encrypt
from ...core.db import get_db

router = APIRouter()

_OUT_COLUMNS = "id,provider,conn_type,label,last4,status,last_validated_at,created_at"


def _to_out(row: dict) -> ProviderConnectionOut:
    return ProviderConnectionOut(
        id=row["id"],
        provider=row["provider"],
        conn_type=row["conn_type"],
        label=row.get("label"),
        last4=row.get("last4"),
        status=row.get("status", "active"),
        last_validated_at=row.get("last_validated_at"),
        created_at=row.get("created_at"),
    )


@router.post("/providers", response_model=ProviderConnectionOut)
async def add_provider(
    req: ProviderAddRequest, user: AuthedUser = Depends(get_current_user)
) -> ProviderConnectionOut:
    base_url = req.base_url or PROVIDER_BASE_URLS.get(req.provider)
    ok, detail = await validate_key(req.provider, req.api_key, base_url)
    if not ok:
        raise HTTPException(400, f"Key validation failed: {detail}")

    db = get_db()
    row = {
        "user_id": user.id,
        "provider": req.provider,
        "conn_type": "byok",
        "label": req.label,
        "secret_enc": encrypt(req.api_key, aad=user.id.encode()),
        "last4": req.api_key[-4:],
        "base_url": req.base_url,
        "status": "active",
        "last_validated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        res = db.table("provider_connections").insert(row).execute()
    except Exception as exc:  # likely unique-violation on (user,provider,conn_type,label)
        raise HTTPException(409, "A connection with this provider/label already exists") from exc
    return _to_out(res.data[0])


@router.get("/providers", response_model=list[ProviderConnectionOut])
async def list_providers(
    user: AuthedUser = Depends(get_current_user),
) -> list[ProviderConnectionOut]:
    db = get_db()
    res = (
        db.table("provider_connections")
        .select(_OUT_COLUMNS)
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_to_out(r) for r in (res.data or [])]


@router.delete("/providers/{conn_id}", status_code=204)
async def delete_provider(conn_id: str, user: AuthedUser = Depends(get_current_user)) -> None:
    db = get_db()
    db.table("provider_connections").delete().eq("id", conn_id).eq("user_id", user.id).execute()


@router.post("/providers/{conn_id}/test", response_model=ProviderTestOut)
async def test_provider(
    conn_id: str, user: AuthedUser = Depends(get_current_user)
) -> ProviderTestOut:
    db = get_db()
    rows = (
        db.table("provider_connections")
        .select("*")
        .eq("id", conn_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Connection not found")
    row = rows[0]
    api_key = decrypt(row["secret_enc"], aad=user.id.encode())
    ok, detail = await validate_key(row["provider"], api_key, row.get("base_url"))
    db.table("provider_connections").update(
        {
            "status": "active" if ok else "invalid",
            "last_validated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", conn_id).eq("user_id", user.id).execute()
    return ProviderTestOut(ok=ok, detail=detail)
