"""
File-based declaration cache for ELM outputs.

Cache key: sha256(domain + ":" + normalized_task_input[:200]).
Storage: one JSON file per key in the cache directory.
TTL-based expiry (default 24 hours).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import structlog

from .declarations import PipelineDeclaration

log = structlog.get_logger()


class DeclarationCache:
    """File-based cache for PipelineDeclaration objects."""

    def __init__(self, cache_dir: str, ttl_hours: int = 24) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_hours * 3600

    @staticmethod
    def make_key(task_input: str, domain: str) -> str:
        """Generate a deterministic cache key from task input and domain."""
        normalized = (domain + ":" + task_input[:200]).strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    def _key_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def get(self, task_input: str, domain: str) -> PipelineDeclaration | None:
        """Retrieve cached declaration if it exists and hasn't expired."""
        cache_key = self.make_key(task_input, domain)
        path = self._key_path(cache_key)

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("elm_cache_read_error", key=cache_key, error=str(exc))
            return None

        # Check TTL
        cached_at = data.get("_cached_at", 0)
        if time.time() - cached_at > self._ttl_seconds:
            log.debug("elm_cache_expired", key=cache_key)
            path.unlink(missing_ok=True)
            return None

        log.debug("elm_cache_hit", key=cache_key, domain=domain)
        return PipelineDeclaration.from_dict(data["declaration"])

    def put(self, declaration: PipelineDeclaration, task_input: str, domain: str) -> None:
        """Store a declaration in the cache."""
        cache_key = self.make_key(task_input, domain)
        path = self._key_path(cache_key)

        payload = {
            "_cached_at": time.time(),
            "declaration": declaration.to_dict(),
        }

        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            log.debug("elm_cache_put", key=cache_key, domain=domain)
        except OSError as exc:
            log.warning("elm_cache_write_error", key=cache_key, error=str(exc))

    def invalidate(self, task_input: str, domain: str) -> None:
        """Remove a specific cache entry."""
        cache_key = self.make_key(task_input, domain)
        self._key_path(cache_key).unlink(missing_ok=True)

    def clear(self) -> int:
        """Remove all cached declarations. Returns count of entries removed."""
        count = 0
        for path in self._cache_dir.glob("*.json"):
            path.unlink(missing_ok=True)
            count += 1
        return count
