"""Best-effort Redis guards for bursty import/write endpoints.

Redis is not the source of truth. PostgreSQL keeps durable import batches and
jobs; these helpers only add cheap rate limits and short-lived duplicate locks.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from . import config


_client = None


def _redis_client():
    global _client
    if not config.REDIS_URL:
        return None
    if _client is not None:
        return _client
    try:
        import redis

        client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        client.ping()
        _client = client
        return client
    except Exception:
        return None


def import_rate_limited(user_id: int) -> bool:
    """Returns True when this workspace exceeded its short-window import limit."""
    client = _redis_client()
    if client is None or config.REDIS_IMPORT_RATE_LIMIT <= 0:
        return False
    key = f"rate:import:v1:{user_id}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, config.REDIS_RATE_LIMIT_WINDOW_SECONDS)
        return count > config.REDIS_IMPORT_RATE_LIMIT
    except Exception:
        return False


def acquire_import_lock(user_id: int, folder_id: int, content: bytes) -> Optional[str]:
    """Acquires a short duplicate-upload lock and returns the lock key.

    ``None`` means no Redis or lock acquisition failure; callers should continue
    and rely on PostgreSQL idempotency.
    """
    client = _redis_client()
    if client is None:
        return None
    digest = hashlib.sha256(content).hexdigest()
    key = f"lock:import:v1:{user_id}:{folder_id}:{digest}"
    try:
        acquired = client.set(key, "1", nx=True, ex=config.REDIS_LOCK_TTL_SECONDS)
        return key if acquired else ""
    except Exception:
        return None
