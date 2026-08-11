"""Optional Redis cache for synthesized TTS audio.

Best-effort, same pattern as chat_cache.py: when Redis is not configured or
fails, callers just re-synthesize the audio via CLOVA Voice.
"""

import hashlib
from typing import Optional

from . import config


_client = None


def _cache_key(text: str, speaker: str) -> str:
    digest = hashlib.sha256(f"{speaker}:{text}".encode("utf-8")).hexdigest()
    return f"tts:audio:v1:{digest}"


def _redis_client():
    global _client
    if not config.REDIS_URL:
        print("[TTS] no REDIS_URL")
        return None
    if _client is not None:
        return _client
    try:
        import redis

        client = redis.Redis.from_url(config.REDIS_URL)
        client.ping()
        _client = client
        print("[TTS] redis connected OK")
    except Exception as exc:
        print("[TTS] redis connect FAILED:", repr(exc))
        return None
    return _client


def get_audio(text: str, speaker: str) -> Optional[bytes]:
    client = _redis_client()
    if client is None:
        return None
    try:
        return client.get(_cache_key(text, speaker))
    except Exception as exc:
        print("[TTS] get_audio FAILED:", repr(exc))
        return None


def set_audio(text: str, speaker: str, audio: bytes) -> None:
    client = _redis_client()
    if client is None:
        print("[TTS] set_audio: no client, skipping")
        return
    try:
        client.set(_cache_key(text, speaker), audio, ex=config.REDIS_TTS_CACHE_TTL_SECONDS)
        print("[TTS] set_audio: wrote key", _cache_key(text, speaker))
    except Exception as exc:
        print("[TTS] set_audio FAILED:", repr(exc))