"""Shared rate limiter instance — avoids circular import between main and routes."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..core.config import settings

# Phase 19: project-wide default limit (applies to every route unless it sets its own)
# + X-RateLimit-Limit/Remaining/Reset response headers so the dashboard can surface quota.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_global],
    headers_enabled=True,
)
