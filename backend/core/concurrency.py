"""
Per-identity concurrency limiting (F-035).

In-process counter that caps how many runs a single identity can have in flight at
once. Best-effort (per-process; distributed pods don't share state) — a cheap guard
against a single user saturating the worker with parallel expensive runs, complementing
the per-IP rate limiter.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from .config import settings


class ConcurrencyLimitExceeded(Exception):
    """Raised when an identity exceeds its in-flight run limit. Maps to HTTP 429."""


_counts: dict[str, int] = {}
_lock = asyncio.Lock()


@asynccontextmanager
async def identity_slot(user_id: str | None):
    """Acquire a concurrency slot for `user_id`. Raises ConcurrencyLimitExceeded if the
    identity already has `MAX_CONCURRENT_PER_IDENTITY` runs in flight. No-op when the
    limit is 0 (unlimited) or no identity is known (single-user / anonymous local mode)."""
    limit = settings.max_concurrent_per_identity
    if limit <= 0 or not user_id:
        yield
        return

    async with _lock:
        current = _counts.get(user_id, 0)
        if current >= limit:
            raise ConcurrencyLimitExceeded(
                f"Identity has {current} runs in flight (limit {limit}). Try again shortly."
            )
        _counts[user_id] = current + 1

    try:
        yield
    finally:
        async with _lock:
            n = _counts.get(user_id, 0) - 1
            if n <= 0:
                _counts.pop(user_id, None)
            else:
                _counts[user_id] = n
