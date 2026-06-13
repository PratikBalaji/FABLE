"""
Scoped repository layer (F-005).

All Supabase queries involving multi-tenant tables MUST go through this module.
Every method injects the caller's identity_id or user_id into the query filter,
so a missing filter can never silently return another user's data.

Usage:
    repo = ScopedRepository(identity_id="<uuid>")
    chunks = repo.memory_chunks().select("*").execute().data

Never call get_db() directly in routes or lifecycle code for user-scoped tables.
"""
from __future__ import annotations

from typing import Any

import structlog

from .db import get_db

log = structlog.get_logger()

# Tables that must always be filtered by user_id (legacy Supabase-auth user).
_USER_ID_TABLES = frozenset({
    "chat_sessions",
    "chat_messages",
    "adversarial_runs",
    "adversarial_messages",
    "memory_chunks",
    "provider_connections",
    "oauth_states",
    "guardrail_events",
    "profiles",
})

# Tables that must always be filtered by identity_id (pseudonymous-first column).
_IDENTITY_ID_TABLES = frozenset({
    "identities",
})


class ScopedRepository:
    """Wraps the service-role Supabase client with mandatory per-user/identity filters.

    Always construct with BOTH identity_id and user_id when available.
    Queries on _USER_ID_TABLES filter by user_id; on _IDENTITY_ID_TABLES by identity_id.
    """

    def __init__(
        self,
        identity_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        if not identity_id and not user_id:
            raise ValueError("ScopedRepository requires at least one of identity_id or user_id")
        self._identity_id = identity_id
        self._user_id = user_id
        self._db = get_db()

    # --- scoped table accessors ------------------------------------------

    def _scoped(self, table: str, id_column: str, id_value: str | None):
        """Return a pre-filtered query builder. Raises if id_value is missing."""
        if not id_value:
            raise ValueError(
                f"ScopedRepository.{table}: {id_column} is required but not provided"
            )
        return self._db.table(table).select("*").eq(id_column, id_value)

    def memory_chunks(self) -> Any:
        return self._scoped("memory_chunks", "user_id", self._user_id)

    def chat_sessions(self) -> Any:
        return self._scoped("chat_sessions", "user_id", self._user_id)

    def chat_messages(self) -> Any:
        return self._scoped("chat_messages", "user_id", self._user_id)

    def adversarial_runs(self) -> Any:
        return self._scoped("adversarial_runs", "user_id", self._user_id)

    def adversarial_messages(self) -> Any:
        return self._scoped("adversarial_messages", "user_id", self._user_id)

    def provider_connections(self) -> Any:
        return self._scoped("provider_connections", "user_id", self._user_id)

    def oauth_states(self) -> Any:
        return self._scoped("oauth_states", "user_id", self._user_id)

    def guardrail_events(self) -> Any:
        return self._scoped("guardrail_events", "user_id", self._user_id)

    def identity(self) -> Any:
        return self._scoped("identities", "id", self._identity_id)

    # --- write helpers ---------------------------------------------------

    def insert(self, table: str, row: dict[str, Any]) -> Any:
        """Insert a row. Automatically injects the scope columns."""
        enriched = dict(row)
        if table in _USER_ID_TABLES and self._user_id and "user_id" not in enriched:
            enriched["user_id"] = self._user_id
        if table in _IDENTITY_ID_TABLES and self._identity_id and "identity_id" not in enriched:
            enriched["identity_id"] = self._identity_id
        return self._db.table(table).insert(enriched).execute()

    def delete_all(self, table: str) -> dict[str, int]:
        """Delete all rows owned by this identity across the given table. Returns count."""
        try:
            id_col, id_val = (
                ("identity_id", self._identity_id)
                if table in _IDENTITY_ID_TABLES
                else ("user_id", self._user_id)
            )
            if not id_val:
                return {table: 0}
            res = self._db.table(table).delete().eq(id_col, id_val).execute()
            return {table: len(res.data or [])}
        except Exception as exc:  # noqa: BLE001
            log.warning("repo_delete_all_failed", table=table, err=str(exc)[:80])
            return {table: -1}
