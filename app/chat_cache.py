"""Optional Redis cache for recent chat context.

PostgreSQL remains the source of truth. This module is intentionally best-effort:
when Redis is not configured or fails, callers fall back to PostgreSQL.
"""

import json
from typing import Dict, List, Optional

from . import config


_client = None


def _cache_key(user_id: int) -> str:
    # Keep the suffix explicit so issue #11 can extend this to video-scoped keys:
    # chat:recent:v1:{workspace_id}:{video_id}
    return f"chat:recent:v1:{user_id}:global"


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
    except Exception:
        return None
    return _client


def _project_messages(messages: List[Dict], *, include_evidence: bool) -> List[Dict]:
    projected = []
    for message in messages:
        item = {"role": message["role"], "content": message["content"]}
        if include_evidence:
            item["evidence"] = message.get("evidence") or []
        projected.append(item)
    return projected


def get_recent(user_id: int, *, include_evidence: bool = False) -> Optional[List[Dict]]:
    client = _redis_client()
    if client is None:
        return None
    try:
        raw_messages = client.lrange(_cache_key(user_id), 0, -1)
        if not raw_messages:
            return None
        messages = [json.loads(raw) for raw in raw_messages]
        return _project_messages(messages, include_evidence=include_evidence)
    except Exception:
        return None


def set_recent(user_id: int, messages: List[Dict]) -> None:
    client = _redis_client()
    if client is None:
        return
    try:
        key = _cache_key(user_id)
        pipe = client.pipeline()
        pipe.delete(key)
        if messages:
            pipe.rpush(key, *[json.dumps(message, ensure_ascii=False, separators=(",", ":")) for message in messages])
            pipe.expire(key, config.REDIS_CHAT_CACHE_TTL_SECONDS)
        pipe.execute()
    except Exception:
        return


def append_recent(user_id: int, message: Dict, *, max_messages: int) -> None:
    client = _redis_client()
    if client is None or max_messages <= 0:
        return
    try:
        key = _cache_key(user_id)
        if not client.exists(key):
            return
        pipe = client.pipeline()
        pipe.rpush(key, json.dumps(message, ensure_ascii=False, separators=(",", ":")))
        pipe.ltrim(key, -max_messages, -1)
        pipe.expire(key, config.REDIS_CHAT_CACHE_TTL_SECONDS)
        pipe.execute()
    except Exception:
        return
