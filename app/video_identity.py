"""Stable, network-free identities for individual YouTube videos."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?]})>}'\""


@dataclass(frozen=True)
class VideoIdentity:
    provider: str
    provider_video_id: str
    canonical_url: str
    start_seconds_hint: Optional[int] = None


def _parse_seconds(value: str) -> Optional[int]:
    """Parse YouTube's numeric and compact ``1h2m3s`` time formats."""
    value = value.strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _start_seconds(parsed) -> Optional[int]:
    query = parse_qs(parsed.query, keep_blank_values=True)
    # YouTube accepts these values in this order for normal share links.
    for key in ("t", "start", "time_continue"):
        values = query.get(key)
        if values:
            seconds = _parse_seconds(values[0])
            if seconds is not None:
                return seconds
    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    for key in ("t", "start", "time_continue"):
        values = fragment.get(key)
        if values:
            seconds = _parse_seconds(values[0])
            if seconds is not None:
                return seconds
    return None


def youtube_video_identity(url: str) -> Optional[VideoIdentity]:
    """Return an identity for a supported YouTube video URL, if present."""
    if not isinstance(url, str):
        return None
    parsed = urlparse(url.strip().rstrip(_TRAILING_PUNCTUATION))
    host = parsed.hostname.lower() if parsed.hostname else ""
    path_parts = [part for part in parsed.path.split("/") if part]

    video_id: Optional[str] = None
    if host == "youtu.be" and path_parts:
        video_id = path_parts[0]
    elif host in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
            video_id = path_parts[1]

    if not video_id or not _VIDEO_ID_RE.fullmatch(video_id):
        return None
    return VideoIdentity(
        provider="youtube",
        provider_video_id=video_id,
        canonical_url="https://www.youtube.com/watch?v=" + quote(video_id, safe="_-"),
        start_seconds_hint=_start_seconds(parsed),
    )


def extract_youtube_urls(text: str) -> list[VideoIdentity]:
    """Extract unique video identities from text in first-seen order."""
    if not isinstance(text, str):
        return []
    identities: list[VideoIdentity] = []
    seen_ids: set[str] = set()
    for match in _URL_RE.finditer(text):
        identity = youtube_video_identity(match.group(0))
        if identity and identity.provider_video_id not in seen_ids:
            identities.append(identity)
            seen_ids.add(identity.provider_video_id)
    return identities


def extract_youtube_url_mentions(text: str) -> list[VideoIdentity]:
    """Extract every YouTube video mention, preserving duplicates and order."""
    if not isinstance(text, str):
        return []
    identities: list[VideoIdentity] = []
    for match in _URL_RE.finditer(text):
        identity = youtube_video_identity(match.group(0))
        if identity:
            identities.append(identity)
    return identities


# Short names keep call sites readable and make the module convenient to adopt.
parse_youtube_url = youtube_video_identity
normalize_youtube_url = youtube_video_identity
