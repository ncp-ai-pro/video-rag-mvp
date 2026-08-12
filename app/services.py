import hashlib
import json
import math
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from . import chat_cache, config
from .db import connection, is_postgres


ANALYSIS_MESSAGES = {
    "queued": "분석 작업을 기다리고 있습니다.",
    "downloading_caption": "자막을 수집하고 있습니다.",
    "transcribing": "자막이 없어 음성을 텍스트로 변환하고 있습니다.",
    "chunking": "자막을 검색 가능한 구간으로 나누고 있습니다.",
    "embedding": "자막 구간의 embedding을 생성하고 있습니다.",
    "completed": "분석이 완료되었습니다. 이제 질문할 수 있습니다.",
    "failed": "분석에 실패했습니다.",
}


def object_storage_is_configured() -> bool:
    """Returns whether the Worker has every credential required for private artifacts."""
    return all(
        (
            config.NCP_OBJECT_STORAGE_ENDPOINT,
            config.NCP_OBJECT_STORAGE_BUCKET,
            config.NCP_OBJECT_STORAGE_ACCESS_KEY,
            config.NCP_OBJECT_STORAGE_SECRET_KEY,
        )
    )


def require_object_storage() -> None:
    if not object_storage_is_configured():
        raise RuntimeError(
            "object_storage_not_configured: set NCP_OBJECT_STORAGE_ENDPOINT, "
            "NCP_OBJECT_STORAGE_BUCKET, NCP_OBJECT_STORAGE_ACCESS_KEY, and "
            "NCP_OBJECT_STORAGE_SECRET_KEY on the Worker"
        )


def _object_storage_client():
    require_object_storage()
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency is installed in production images
        raise RuntimeError("boto3 is required for Object Storage uploads") from exc
    return boto3.client(
        "s3",
        endpoint_url=config.NCP_OBJECT_STORAGE_ENDPOINT,
        region_name=config.NCP_OBJECT_STORAGE_REGION,
        aws_access_key_id=config.NCP_OBJECT_STORAGE_ACCESS_KEY,
        aws_secret_access_key=config.NCP_OBJECT_STORAGE_SECRET_KEY,
    )


def upload_artifact_file(local_path: Path, object_key: str, content_type: Optional[str] = None) -> str:
    """Uploads a Worker-created artifact to the configured private Object Storage bucket."""
    extra_args = {"ContentType": content_type} if content_type else None
    client = _object_storage_client()
    if extra_args:
        client.upload_file(str(local_path), config.NCP_OBJECT_STORAGE_BUCKET, object_key, ExtraArgs=extra_args)
    else:
        client.upload_file(str(local_path), config.NCP_OBJECT_STORAGE_BUCKET, object_key)
    return object_key


def upload_artifact_json(payload: Dict, object_key: str) -> str:
    """Stores provider responses and normalized transcripts as UTF-8 JSON artifacts."""
    _object_storage_client().put_object(
        Bucket=config.NCP_OBJECT_STORAGE_BUCKET,
        Key=object_key,
        Body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )
    return object_key


def speech_data_key(object_key: str) -> str:
    """Converts a bucket key to the path relative to the Speech domain input prefix."""
    prefix = config.OBJECT_STORAGE_STT_INPUT_PREFIX
    if not prefix:
        return "/" + object_key.lstrip("/")
    expected = prefix + "/"
    if not object_key.startswith(expected):
        raise ValueError(f"speech input object must be below {prefix}/")
    return "/" + object_key[len(expected) :]


def transcribe_object_storage(object_key: str) -> Dict:
    """Requests CLOVA Speech long-form recognition for an object inside the domain input prefix."""
    if not config.CLOVA_SPEECH_INVOKE_URL or not config.CLOVA_SPEECH_API_KEY:
        raise RuntimeError(
            "clova_speech_not_configured: set CLOVA_SPEECH_INVOKE_URL and CLOVA_SPEECH_API_KEY on the Worker"
        )
    response = httpx.post(
        config.CLOVA_SPEECH_INVOKE_URL.rstrip("/") + "/recognizer/object-storage",
        headers={
            "Accept": "application/json;UTF-8",
            "Content-Type": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": config.CLOVA_SPEECH_API_KEY,
        },
        json={
            "dataKey": speech_data_key(object_key),
            "language": config.CLOVA_SPEECH_LANGUAGE,
            "completion": "sync",
            "wordAlignment": True,
            "fullText": True,
            "noiseFiltering": True,
        },
        timeout=1800,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result")
    if result and result not in {"SUCCEEDED", "COMPLETED"}:
        raise RuntimeError(f"clova_speech_failed: {result}: {payload.get('message', '')}".rstrip())
    return payload


def normalize_clova_speech_segments(payload: Dict) -> List[Dict]:
    """Maps CLOVA Speech millisecond segments to the transcript contract used by RAG."""
    normalized = []
    for segment in payload.get("segments") or []:
        text = " ".join(str(segment.get("text") or "").split())
        try:
            start_seconds = float(segment["start"]) / 1000
            end_seconds = float(segment["end"]) / 1000
        except (KeyError, TypeError, ValueError):
            continue
        if text and end_seconds > start_seconds:
            normalized.append(
                {
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "text": text,
                }
            )
    if not normalized:
        raise RuntimeError("clova_speech_empty_transcript")
    return normalized


def metadata_text(video: Dict) -> str:
    return "\n".join(part for part in [video["title"], video.get("description", "")] if part).strip()


def _tokens(text: str) -> Iterable[str]:
    return re.findall(r"[\w가-힣]{2,}", text.lower())


def _mock_embedding(text: str, dimensions: int = 1024) -> List[float]:
    """Deterministic token hashing used only for local API smoke tests."""
    vector = [0.0] * dimensions
    for token in _tokens(text):
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dimensions
        vector[index] += 1.0
    return _normalize(vector)


def _normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def has_video_embedding(video_id: int) -> bool:
    """Returns whether this video already has transcript chunks embedded."""
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM transcript_chunks WHERE video_id=? LIMIT 1",
            (video_id,),
        ).fetchone()
    return row is not None


def embedding(text: str) -> List[float]:
    if config.EMBEDDING_PROVIDER == "mock":
        return _mock_embedding(text)
    if config.EMBEDDING_PROVIDER != "clova":
        raise RuntimeError("EMBEDDING_PROVIDER must be mock or clova")
    if not config.CLOVASTUDIO_API_KEY:
        raise RuntimeError("CLOVASTUDIO_API_KEY is required for EMBEDDING_PROVIDER=clova")

    response = httpx.post(
        "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2/",
        headers={
            "Authorization": "Bearer " + config.CLOVASTUDIO_API_KEY,
            "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=60,
    )
    response.raise_for_status()
    return _normalize(response.json()["result"]["embedding"])


def _reset_seconds(response: httpx.Response) -> Optional[float]:
    """Reads CLOVA Studio's `23s` rate-limit reset header when it is present."""
    value = response.headers.get("x-ratelimit-reset-requests", "")
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s?\s*", value)
    return float(match.group(1)) if match else None


class EmbeddingRateLimiter:
    """Paces Worker-only embedding calls and retries transient CLOVA Studio 429 responses."""

    def __init__(
        self,
        *,
        min_interval_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        request_embedding: Callable[[str], List[float]] = embedding,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.max_retries = max(0, max_retries)
        self.backoff_base_seconds = max(0.0, backoff_base_seconds)
        self.request_embedding = request_embedding
        self.clock = clock
        self.sleep = sleep
        self.next_request_at = 0.0

    def embed(self, text: str) -> List[float]:
        if config.EMBEDDING_PROVIDER != "clova":
            return self.request_embedding(text)

        for attempt in range(self.max_retries + 1):
            wait_seconds = self.next_request_at - self.clock()
            if wait_seconds > 0:
                self.sleep(wait_seconds)
            requested_at = self.clock()
            self.next_request_at = requested_at + self.min_interval_seconds
            try:
                return self.request_embedding(text)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt >= self.max_retries:
                    raise
                reset_seconds = _reset_seconds(exc.response)
                exponential_seconds = self.backoff_base_seconds * (2**attempt)
                self.next_request_at = self.clock() + max(reset_seconds or 0, exponential_seconds)

        raise RuntimeError("embedding retry loop exhausted")  # pragma: no cover


def cosine(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def enqueue(kind: str, resource_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs(kind, resource_id, progress_stage, progress_message, updated_at)
            VALUES (?, ?, 'queued', ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            RETURNING id
            """,
            (kind, resource_id, ANALYSIS_MESSAGES["queued"]),
        ).fetchone()
        return row["id"]


def enqueue_analysis(video_id: int) -> int:
    """Creates the queued job and the video-visible progress in one DB transaction."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE videos
            SET analysis_status='queued', analysis_stage='queued', analysis_message=?,
                analysis_error=NULL, analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (ANALYSIS_MESSAGES["queued"], video_id),
        )
        row = conn.execute(
            """
            INSERT INTO jobs(kind, resource_id, status, progress_stage, progress_message, updated_at)
            VALUES ('analyze_video', ?, 'queued', 'queued', ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            RETURNING id
            """,
            (video_id, ANALYSIS_MESSAGES["queued"]),
        ).fetchone()
        return row["id"]


def update_analysis_progress(job_id: int, video_id: int, stage: str, message: Optional[str] = None):
    """Persists a Worker-owned in-progress stage; FastAPI only reads this state."""
    if stage not in ANALYSIS_MESSAGES:
        raise ValueError("unknown analysis progress stage")
    progress_message = message or ANALYSIS_MESSAGES[stage]
    with connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status='running', progress_stage=?, progress_message=?, error_message=NULL,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (stage, progress_message, job_id),
        )
        conn.execute(
            """
            UPDATE videos
            SET analysis_status='running', analysis_stage=?, analysis_message=?, analysis_error=NULL,
                analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (stage, progress_message, video_id),
        )


def record_analysis_artifact(
    video_id: int, job_id: int, kind: str, object_key: str, content_type: Optional[str] = None
) -> None:
    """Keeps the immutable Object Storage key alongside the video/job that produced it."""
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO analysis_artifacts(video_id, job_id, kind, object_key, content_type)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id, kind) DO UPDATE SET
                object_key=excluded.object_key, content_type=excluded.content_type
            """,
            (video_id, job_id, kind, object_key, content_type),
        )


def finish_analysis(job_id: int, video_id: int, error: Optional[str] = None):
    """Writes the terminal job and video state together after Worker processing."""
    failed = error is not None
    stage = "failed" if failed else "completed"
    message = str(error)[:2000] if failed else ANALYSIS_MESSAGES["completed"]
    status = "failed" if failed else "succeeded"
    with connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status=?, progress_stage=?, progress_message=?, error_message=?, finished_at=CURRENT_TIMESTAMP,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (status, stage, message, message if failed else None, job_id),
        )
        conn.execute(
            """
            UPDATE videos
            SET analysis_status=?, analysis_stage=?, analysis_message=?, analysis_error=?,
                analyzed_at=CASE WHEN ?='succeeded' THEN CURRENT_TIMESTAMP ELSE analyzed_at END,
                analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (status, stage, message, message if failed else None, status, video_id),
        )


def analysis_event_state(video_id: int, user_id: int) -> Optional[Dict]:
    """Returns only the newest analysis job that belongs to the current workspace."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT videos.id AS video_id, videos.analysis_status, videos.analysis_stage,
                   videos.analysis_message, videos.analysis_error, videos.analysis_updated_at,
                   jobs.id AS job_id, jobs.status AS job_status, jobs.progress_stage,
                   jobs.progress_message, jobs.error_message, jobs.updated_at
            FROM videos
            JOIN channels ON channels.id=videos.channel_id
            LEFT JOIN jobs ON jobs.id=(
                SELECT id FROM jobs
                WHERE kind='analyze_video' AND resource_id=videos.id
                ORDER BY id DESC LIMIT 1
            )
            WHERE videos.id=? AND channels.user_id=?
            """,
            (video_id, user_id),
        ).fetchone()
    if not row or row["job_id"] is None:
        return None
    state = dict(row)
    updated_at = state["updated_at"] or state["analysis_updated_at"]
    if isinstance(updated_at, datetime):
        updated_at = updated_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    elif updated_at and "T" not in updated_at:
        updated_at = updated_at.replace(" ", "T") + "Z"
    return {
        "video_id": state["video_id"],
        "job_id": state["job_id"],
        "status": state["job_status"],
        "progress": {
            "stage": state["progress_stage"] or state["analysis_stage"] or state["job_status"],
            "message": state["progress_message"] or state["analysis_message"] or ANALYSIS_MESSAGES["queued"],
        },
        "error": state["error_message"] or state["analysis_error"],
        "updated_at": updated_at,
    }


def video_belongs_to_workspace(user_id: int, video_id: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT videos.id
            FROM videos JOIN channels ON channels.id=videos.channel_id
            WHERE videos.id=? AND channels.user_id=?
            """,
            (video_id, user_id),
        ).fetchone()
    return row is not None


def upsert_video(channel_id: int, raw: Dict) -> int:
    video = {
        "platform_video_id": raw["platform_video_id"],
        "title": raw["title"],
        "description": raw.get("description") or "",
        "url": str(raw["url"]),
        "thumbnail_url": str(raw["thumbnail_url"]) if raw.get("thumbnail_url") else None,
        "duration_seconds": raw.get("duration_seconds"),
        "uploaded_at": raw.get("uploaded_at"),
    }
    vector = json.dumps(embedding(metadata_text(video)))
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO videos (
                channel_id, platform_video_id, title, description, url, thumbnail_url,
                duration_seconds, uploaded_at, metadata_embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id, platform_video_id) DO UPDATE SET
                title=excluded.title, description=excluded.description, url=excluded.url,
                thumbnail_url=excluded.thumbnail_url, duration_seconds=excluded.duration_seconds,
                uploaded_at=excluded.uploaded_at, metadata_embedding=excluded.metadata_embedding
            RETURNING id
            """,
            (
                channel_id,
                video["platform_video_id"],
                video["title"],
                video["description"],
                video["url"],
                video["thumbnail_url"],
                video["duration_seconds"],
                video["uploaded_at"],
                vector,
            ),
        ).fetchone()
        return row["id"]


def _yt_dlp_failure_message(result: subprocess.CompletedProcess) -> str:
    output = "\n".join(part for part in (result.stderr, result.stdout) if part)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    error_lines = [line for line in lines if "error:" in line.lower()]
    return (error_lines or lines or ["yt-dlp exited without an error message"])[-1][:500]


def _youtube_video_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/", 1)[0] or None
    if host not in {"youtube.com", "music.youtube.com"}:
        return None
    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
        return parts[1]
    return None


def _video_metadata_from_ytdlp(item: Dict, fallback_video_id: Optional[str] = None) -> Dict:
    video_id = item.get("id") or fallback_video_id
    if not video_id:
        raise RuntimeError("yt-dlp did not return a video id")
    return {
        "platform_video_id": video_id,
        "title": item.get("title") or video_id,
        "description": item.get("description") or "",
        "url": item.get("webpage_url") or "https://www.youtube.com/watch?v=" + video_id,
        "thumbnail_url": item.get("thumbnail"),
        "duration_seconds": item.get("duration"),
        "uploaded_at": item.get("upload_date"),
    }


def collect_channel_metadata(url: str) -> List[Dict]:
    """Fetches channel/playlist metadata, or a single video when the registered URL is a watch URL."""
    single_video_id = _youtube_video_id(url)
    if single_video_id:
        result = subprocess.run(
            [config.YTDLP_BIN, "--dump-single-json", "--skip-download", "--no-playlist", url],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode:
            raise RuntimeError("video_metadata_failed: " + _yt_dlp_failure_message(result))
        return [_video_metadata_from_ytdlp(json.loads(result.stdout), single_video_id)]

    result = subprocess.run(
        [config.YTDLP_BIN, "--flat-playlist", "--dump-json", "--skip-download", url],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError("channel_metadata_failed: " + _yt_dlp_failure_message(result))
    videos = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        videos.append(_video_metadata_from_ytdlp(json.loads(line)))
    return videos


def import_transcript(
    video_id: int,
    segments: List[Dict],
    *,
    paragraphs: Optional[List[Dict]] = None,
    mark_analyzed: bool = True,
    embed_text: Callable[[str], List[float]] = embedding,
):
    if paragraphs is None:
        paragraphs = [
            {
                "paragraph_index": index,
                "start_seconds": segment["start_seconds"],
                "end_seconds": segment["end_seconds"],
                "text": segment["text"],
            }
            for index, segment in enumerate(segments)
        ]
        segments = [
            {
                **segment,
                "paragraph_index": index,
                "chunk_index": 0,
            }
            for index, segment in enumerate(segments)
        ]

    with connection() as conn:
        exists = conn.execute("SELECT id FROM videos WHERE id=?", (video_id,)).fetchone()
        if not exists:
            raise LookupError("video not found")
        conn.execute("DELETE FROM transcript_chunks WHERE video_id=?", (video_id,))
        conn.execute("DELETE FROM transcript_paragraphs WHERE video_id=?", (video_id,))
        paragraph_ids = {}
        for index, paragraph in enumerate(paragraphs):
            start_seconds = paragraph["start_seconds"]
            end_seconds = paragraph["end_seconds"]
            if end_seconds <= start_seconds:
                raise ValueError("paragraph end_seconds must be greater than start_seconds")
            paragraph_index = paragraph.get("paragraph_index", index)
            row = conn.execute(
                """
                INSERT INTO transcript_paragraphs(video_id, paragraph_index, start_seconds, end_seconds, text)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (video_id, paragraph_index, start_seconds, end_seconds, paragraph["text"]),
            ).fetchone()
            paragraph_ids[paragraph_index] = row["id"]
        for segment in segments:
            if segment["end_seconds"] <= segment["start_seconds"]:
                raise ValueError("end_seconds must be greater than start_seconds")
            paragraph_id = paragraph_ids.get(segment.get("paragraph_index"))
            conn.execute(
                """
                INSERT INTO transcript_chunks(
                    video_id, paragraph_id, chunk_index, start_seconds, end_seconds, text, embedding
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    paragraph_id,
                    segment.get("chunk_index", 0),
                    segment["start_seconds"],
                    segment["end_seconds"],
                    segment["text"],
                    json.dumps(embed_text(segment["text"])),
                ),
            )
        if mark_analyzed:
            conn.execute(
                """
                UPDATE videos
                SET analysis_status='succeeded', analysis_stage='completed', analysis_message=?,
                    analysis_error=NULL, analyzed_at=CURRENT_TIMESTAMP,
                    analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (ANALYSIS_MESSAGES["completed"], video_id),
            )


def find_metadata(user_id: int, query: str, limit: int) -> List[Dict]:
    query_vector = embedding(query)
    with connection() as conn:
        if is_postgres():
            rows = conn.execute(
                """
                SELECT videos.id, videos.title, videos.description, videos.url, videos.thumbnail_url,
                       videos.duration_seconds, videos.uploaded_at,
                       1 - (videos.metadata_embedding <=> ?::vector) AS score
                FROM videos JOIN channels ON channels.id=videos.channel_id
                WHERE channels.user_id=? AND videos.metadata_embedding IS NOT NULL
                ORDER BY videos.metadata_embedding <=> ?::vector
                LIMIT ?
                """,
                (json.dumps(query_vector), user_id, json.dumps(query_vector), limit),
            ).fetchall()
            return [
                {
                    "video_id": row["id"],
                    "title": row["title"],
                    "description": row["description"],
                    "url": row["url"],
                    "thumbnail_url": row["thumbnail_url"],
                    "duration_seconds": row["duration_seconds"],
                    "uploaded_at": row["uploaded_at"],
                    "score": round(float(row["score"]), 4),
                    "basis": "제목과 영상 설명의 pgvector cosine similarity",
                }
                for row in rows
            ]
        rows = conn.execute(
            """
            SELECT videos.id, videos.title, videos.description, videos.url, videos.thumbnail_url,
                   videos.duration_seconds, videos.uploaded_at, videos.metadata_embedding
            FROM videos JOIN channels ON channels.id=videos.channel_id
            WHERE channels.user_id=?
            """,
            (user_id,),
        ).fetchall()
    results = []
    for row in rows:
        if not row["metadata_embedding"]:
            continue
        results.append(
            {
                "video_id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "url": row["url"],
                "thumbnail_url": row["thumbnail_url"],
                "duration_seconds": row["duration_seconds"],
                "uploaded_at": row["uploaded_at"],
                "score": round(cosine(query_vector, json.loads(row["metadata_embedding"])), 4),
                "basis": "제목과 영상 설명의 embedding 유사도",
            }
        )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def _split_evidence_sentences(text: str) -> List[str]:
    normalized = " ".join(str(text or "").split())
    sentences = [match.group(0).strip() for match in re.finditer(r"[^.!?。！？]+(?:[.!?。！？]+|$)", normalized)]
    return [sentence for sentence in sentences if sentence]


def _token_overlap_highlight(query: str, text: str) -> Optional[Dict]:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return None
    best_sentence, best_matches = "", 0
    for sentence in _split_evidence_sentences(text):
        sentence_tokens = set(_tokens(sentence))
        matches = sum(
            1
            for query_token in query_tokens
            if any(query_token in sentence_token or sentence_token in query_token for sentence_token in sentence_tokens)
        )
        if matches > best_matches:
            best_sentence, best_matches = sentence, matches
    if not best_sentence or best_matches == 0:
        return None
    return {
        "text": best_sentence,
        "method": "query_token_overlap",
        "score": round(best_matches / len(query_tokens), 4),
    }


def _semantic_similarity_highlight(query_vector: List[float], text: str) -> Optional[Dict]:
    sentences = _split_evidence_sentences(text)
    if not sentences:
        return None
    best_sentence = ""
    best_score = -1.0
    for sentence in sentences:
        score = cosine(query_vector, embedding(sentence))
        if score > best_score:
            best_sentence = sentence
            best_score = score
    if not best_sentence or best_score <= 0:
        return None
    return {
        "text": best_sentence,
        "method": "sentence_embedding_similarity",
        "score": round(best_score, 4),
    }


def _decorate_evidence(
    evidence: List[Dict], query: str, evidence_mode: str, query_vector: Optional[List[float]] = None
) -> List[Dict]:
    decorated = []
    for index, item in enumerate(evidence, start=1):
        enriched = {**item, "rank": index, "is_primary": index == 1}
        if evidence_mode == "precise":
            highlight = _token_overlap_highlight(query, item.get("quote") or item.get("context") or "")
            if highlight:
                enriched["highlight"] = highlight
        elif evidence_mode == "ultra" and query_vector is not None:
            highlight = _semantic_similarity_highlight(query_vector, item.get("quote") or item.get("context") or "")
            if highlight:
                enriched["highlight"] = highlight
        decorated.append(enriched)
    return decorated


def find_evidence(
    user_id: int,
    query: str,
    limit: int,
    video_id: Optional[int] = None,
    evidence_mode: str = "simple",
    folder_id: Optional[int] = None,
) -> List[Dict]:
    query_vector = embedding(query)
    video_filter = " AND videos.id=?" if video_id is not None else ""
    video_params = (video_id,) if video_id is not None else ()
    folder_join = " JOIN folder_videos ON folder_videos.video_id=videos.id" if folder_id is not None else ""
    folder_filter = " AND folder_videos.folder_id=?" if folder_id is not None else ""
    folder_params = (folder_id,) if folder_id is not None else ()
    expanded_limit = max(limit * 4, limit)
    with connection() as conn:
        if is_postgres():
            rows = conn.execute(
                """
                SELECT chunks.id AS chunk_id, chunks.paragraph_id,
                       chunks.start_seconds, chunks.end_seconds, chunks.text,
                       paragraphs.text AS paragraph_text,
                       videos.id AS video_id, videos.title, videos.url,
                       1 - (chunks.embedding <=> ?::vector) AS score
                FROM transcript_chunks AS chunks
                LEFT JOIN transcript_paragraphs AS paragraphs ON paragraphs.id = chunks.paragraph_id
                JOIN videos ON videos.id = chunks.video_id
                """
                + folder_join
                + """
                JOIN channels ON channels.id = videos.channel_id
                WHERE videos.analysis_status IN ('succeeded', 'ready') AND channels.user_id=?"""
                + video_filter
                + folder_filter
                + """
                ORDER BY chunks.embedding <=> ?::vector
                LIMIT ?
                """,
                (
                    json.dumps(query_vector),
                    user_id,
                    *video_params,
                    *folder_params,
                    json.dumps(query_vector),
                    expanded_limit,
                ),
            ).fetchall()
            evidence = []
            seen = set()
            for row in rows:
                dedupe_key = (row["video_id"], row["paragraph_id"] or row["chunk_id"])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                separator = "&" if "?" in row["url"] else "?"
                evidence.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "paragraph_id": row["paragraph_id"],
                        "video_id": row["video_id"],
                        "title": row["title"],
                        "start_seconds": row["start_seconds"],
                        "end_seconds": row["end_seconds"],
                        "quote": row["text"],
                        "context": row["paragraph_text"] or row["text"],
                        "url": row["url"] + separator + "t=" + str(int(row["start_seconds"])) + "s",
                        "score": round(float(row["score"]), 4),
                    }
                )
                if len(evidence) >= limit:
                    break
            return _decorate_evidence(evidence, query, evidence_mode, query_vector)
        rows = conn.execute(
            """
            SELECT chunks.id AS chunk_id, chunks.paragraph_id,
                   chunks.start_seconds, chunks.end_seconds, chunks.text, chunks.embedding,
                   paragraphs.text AS paragraph_text,
                   videos.id AS video_id, videos.title, videos.url
            FROM transcript_chunks AS chunks
            LEFT JOIN transcript_paragraphs AS paragraphs ON paragraphs.id = chunks.paragraph_id
            JOIN videos ON videos.id = chunks.video_id
            """
            + folder_join
            + """
            JOIN channels ON channels.id = videos.channel_id
            WHERE videos.analysis_status IN ('succeeded', 'ready') AND channels.user_id=?"""
            + video_filter
            + folder_filter
            + """
            """,
            (user_id, *video_params, *folder_params),
        ).fetchall()
    evidence = []
    for row in rows:
        separator = "&" if "?" in row["url"] else "?"
        evidence.append(
            {
                "chunk_id": row["chunk_id"],
                "paragraph_id": row["paragraph_id"],
                "video_id": row["video_id"],
                "title": row["title"],
                "start_seconds": row["start_seconds"],
                "end_seconds": row["end_seconds"],
                "quote": row["text"],
                "context": row["paragraph_text"] or row["text"],
                "url": row["url"] + separator + "t=" + str(int(row["start_seconds"])) + "s",
                "score": round(cosine(query_vector, json.loads(row["embedding"])), 4),
            }
        )
    deduped = []
    seen = set()
    for item in sorted(evidence, key=lambda item: item["score"], reverse=True):
        dedupe_key = (item["video_id"], item["paragraph_id"] or item["chunk_id"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return _decorate_evidence(deduped, query, evidence_mode, query_vector)


def _chat_scope_condition(video_id: Optional[int], folder_id: Optional[int]) -> str:
    video_condition = "video_id IS NULL" if video_id is None else "video_id=?"
    folder_condition = "folder_id IS NULL" if folder_id is None else "folder_id=?"
    return folder_condition + " AND " + video_condition


def _chat_scope_params(video_id: Optional[int], folder_id: Optional[int]) -> tuple:
    params = []
    if folder_id is not None:
        params.append(folder_id)
    if video_id is not None:
        params.append(video_id)
    return tuple(params)


def record_chat_message(
    user_id: int,
    role: str,
    content: str,
    evidence: Optional[List[Dict]] = None,
    video_id: Optional[int] = None,
    folder_id: Optional[int] = None,
) -> None:
    """Appends a turn and prunes the workspace's history to the configured retention window."""
    keep = max(0, config.CHAT_HISTORY_TURNS) * 2
    evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) if evidence else None
    scope_condition = _chat_scope_condition(video_id, folder_id)
    scope_params = _chat_scope_params(video_id, folder_id)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages(user_id, folder_id, video_id, role, content, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, folder_id, video_id, role, content, evidence_json),
        )
        conn.execute(
            f"""
            DELETE FROM chat_messages
            WHERE user_id=? AND {scope_condition} AND id NOT IN (
                SELECT id FROM chat_messages WHERE user_id=? AND {scope_condition} ORDER BY id DESC LIMIT ?
            )
            """,
            (user_id, *scope_params, user_id, *scope_params, keep),
        )
    message = {"role": role, "content": content}
    if evidence:
        message["evidence"] = evidence
    if folder_id is None and video_id is None:
        chat_cache.append_recent(user_id, message, max_messages=keep)


def recent_chat_history(
    user_id: int,
    *,
    include_evidence: bool = False,
    video_id: Optional[int] = None,
    folder_id: Optional[int] = None,
) -> List[Dict]:
    """Returns this workspace's last CHAT_HISTORY_TURNS turns in chronological order."""
    limit = max(0, config.CHAT_HISTORY_TURNS) * 2
    if limit == 0:
        return []
    scope_condition = _chat_scope_condition(video_id, folder_id)
    scope_params = _chat_scope_params(video_id, folder_id)
    if not include_evidence and video_id is None and folder_id is None:
        cached = chat_cache.get_recent(user_id, include_evidence=False)
        if cached is not None:
            return cached
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT role, content, evidence_json
            FROM chat_messages
            WHERE user_id=? AND {scope_condition}
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, *scope_params, limit),
        ).fetchall()
    history = []
    for row in reversed(rows):
        item = {"role": row["role"], "content": row["content"]}
        if include_evidence:
            try:
                evidence_json = row["evidence_json"]
                item["evidence"] = json.loads(evidence_json) if evidence_json else []
            except (TypeError, ValueError, json.JSONDecodeError):
                item["evidence"] = []
        history.append(item)
    if not include_evidence and video_id is None and folder_id is None:
        chat_cache.set_recent(user_id, [{"role": item["role"], "content": item["content"]} for item in history])
    return history


def _chat_message_item(row: Dict) -> Dict:
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    elif created_at and "T" not in created_at:
        created_at = str(created_at).replace(" ", "T") + "Z"
    try:
        evidence = json.loads(row["evidence_json"]) if row["evidence_json"] else []
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence = []
    return {
        "id": row["id"],
        "folder_id": row["folder_id"],
        "video_id": row["video_id"],
        "role": row["role"],
        "content": row["content"],
        "evidence": evidence,
        "created_at": created_at,
    }


def paged_chat_history(
    user_id: int,
    *,
    limit: int = 20,
    before_id: Optional[int] = None,
    video_id: Optional[int] = None,
    folder_id: Optional[int] = None,
) -> Dict:
    """Returns a cursor page for UI history; LLM context still uses recent_chat_history()."""
    page_size = min(max(limit, 1), 100)
    scope_condition = _chat_scope_condition(video_id, folder_id)
    query = """
        SELECT id, folder_id, video_id, role, content, evidence_json, created_at
        FROM chat_messages
        WHERE user_id=? AND """ + scope_condition + """
    """
    params: List = [user_id]
    params.extend(_chat_scope_params(video_id, folder_id))
    if before_id is not None:
        query += " AND id < ?"
        params.append(before_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(page_size + 1)
    with connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items = [_chat_message_item(row) for row in reversed(rows)]
    return {
        "items": items,
        "messages": items,
        "has_more": has_more,
        "next_cursor": items[0]["id"] if has_more and items else None,
    }


def _chat_instruction(evidence: List[Dict]) -> str:
    context = "\n\n".join(
        "[{} {}-{}]\n{}".format(
            item["title"], item["start_seconds"], item["end_seconds"], item.get("context") or item["quote"]
        )
        for item in evidence
    )
    return (
        "주어진 영상 자막 근거만 사용해 한국어로 답하세요. 근거에 없는 사실은 모른다고 말하세요. "
        "시간 표시는 API가 별도로 반환하므로 본문에 임의의 시간을 만들지 마세요.\n\n근거:\n" + context
    )


def _chat_payload(question: str, evidence: List[Dict], history: Optional[List[Dict[str, str]]] = None) -> Dict:
    return {
        "messages": [
            {"role": "system", "content": _chat_instruction(evidence)},
            *(history or []),
            {"role": "user", "content": question},
        ],
        "maxTokens": 500,
        "temperature": 0.2,
        "topP": 0.8,
        "topK": 0,
        "repetitionPenalty": 1.1,
    }


def _chat_headers(*, stream: bool = False) -> Dict[str, str]:
    headers = {
        "Authorization": "Bearer " + config.CLOVASTUDIO_API_KEY,
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    if stream:
        headers["Accept"] = "text/event-stream"
    return headers


def answer(question: str, evidence: List[Dict], history: Optional[List[Dict[str, str]]] = None) -> str:
    if not evidence:
        return "분석이 완료된 영상 자막에서 질문과 연결되는 근거를 찾지 못했습니다. 먼저 영상을 분석해 주세요."
    if config.CHAT_PROVIDER == "mock":
        return "로컬 테스트 모드입니다. 아래 근거 구간을 기준으로 CLOVA Chat 답변을 생성하게 됩니다."
    if config.CHAT_PROVIDER != "clova":
        raise RuntimeError("CHAT_PROVIDER must be mock or clova")
    if not config.CLOVASTUDIO_API_KEY:
        raise RuntimeError("CLOVASTUDIO_API_KEY is required for CHAT_PROVIDER=clova")
    response = httpx.post(
        "https://clovastudio.stream.ntruss.com/v3/chat-completions/" + config.CLOVA_MODEL,
        headers=_chat_headers(),
        json=_chat_payload(question, evidence, history),
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["result"]["message"]["content"]

def _summary_payload(qa_text: str) -> Dict:
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "아래 질문과 답변들을 종합해서 핵심 내용을 3~5문장으로 자연스럽게 요약하세요. "
                    "목록이 아니라 하나의 문단으로 작성하세요."
                ),
            },
            {"role": "user", "content": qa_text},
        ],
        "maxTokens": 400,
        "temperature": 0.3,
        "topP": 0.8,
        "topK": 0,
        "repetitionPenalty": 1.1,
    }


def summarize_chat_transcript(qa_pairs: List[Dict]) -> str:
    if not qa_pairs:
        return "요약할 대화 내용이 없습니다."
    qa_text = "\n\n".join(f"질문: {pair['question']}\n답변: {pair['answer']}" for pair in qa_pairs)
    if config.CHAT_PROVIDER == "mock":
        return "로컬 테스트 모드 요약본입니다. 실제 CLOVA 연결 시 대화 내용을 종합한 요약이 표시됩니다."
    if config.CHAT_PROVIDER != "clova":
        raise RuntimeError("CHAT_PROVIDER must be mock or clova")
    if not config.CLOVASTUDIO_API_KEY:
        raise RuntimeError("CLOVASTUDIO_API_KEY is required for CHAT_PROVIDER=clova")
    response = httpx.post(
        "https://clovastudio.stream.ntruss.com/v3/chat-completions/" + config.CLOVA_MODEL,
        headers=_chat_headers(),
        json=_summary_payload(qa_text),
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["result"]["message"]["content"]


def _export_data(
    user_id: int, video_id: Optional[int], message_ids: Optional[List[int]]
) -> "tuple[str, List[Dict]]":
    """Returns (title, qa_pairs) scoped to one video (or the whole workspace) and
    filtered to the selected question turns when message_ids is given."""
    if video_id is not None:
        with connection() as conn:
            video_row = conn.execute("SELECT title FROM videos WHERE id=?", (video_id,)).fetchone()
        title = video_row["title"] if video_row else "선택한 영상"
        scope_sql = "video_id=?"
        scope_params: tuple = (video_id,)
    else:
        title = "전체 대화"
        scope_sql = "1=1"
        scope_params = ()

    with connection() as conn:
        rows = conn.execute(
            f"SELECT id, role, content FROM chat_messages WHERE user_id=? AND {scope_sql} ORDER BY id ASC",
            (user_id, *scope_params),
        ).fetchall()

    wanted_ids = set(message_ids) if message_ids else None
    qa_pairs: List[Dict] = []
    pending_question: Optional[str] = None
    pending_question_id: Optional[int] = None
    for row in rows:
        if row["role"] == "user":
            pending_question = row["content"]
            pending_question_id = row["id"]
        elif pending_question is not None:
            if wanted_ids is None or pending_question_id in wanted_ids:
                qa_pairs.append({"question": pending_question, "answer": row["content"]})
            pending_question = None
            pending_question_id = None
    return title, qa_pairs


def export_chat_transcript_txt(
    user_id: int, video_id: Optional[int] = None, message_ids: Optional[List[int]] = None
) -> str:
    title, qa_pairs = _export_data(user_id, video_id, message_ids)
    divider = "-" * 20
    lines = [title, "", divider, "", summarize_chat_transcript(qa_pairs), "", divider, ""]
    for index, pair in enumerate(qa_pairs, start=1):
        lines.append(f"질문 {index}. {pair['question']}")
        lines.append(f"답변 {index}. {pair['answer']}")
        if index != len(qa_pairs):
            lines.append("")
            lines.append(divider)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_PDF_FONT_NAME: Optional[str] = None


def _pdf_font_path() -> str:
    candidates = [
        config.PDF_FONT_PATH,
        r"C:\Windows\Fonts\malgun.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansKR-Regular.otf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    raise RuntimeError(
        "PDF에 사용할 한글 폰트를 찾을 수 없습니다. PDF_FONT_PATH 환경변수에 TTF 폰트 경로를 설정하세요."
    )


def _ensure_pdf_font() -> str:
    global _PDF_FONT_NAME
    if _PDF_FONT_NAME is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("ExportKorean", _pdf_font_path()))
        _PDF_FONT_NAME = "ExportKorean"
    return _PDF_FONT_NAME


def _pdf_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def export_chat_transcript_pdf(
    user_id: int, video_id: Optional[int] = None, message_ids: Optional[List[int]] = None
) -> bytes:
    import io

    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    title, qa_pairs = _export_data(user_id, video_id, message_ids)
    summary = summarize_chat_transcript(qa_pairs)
    font_name = _ensure_pdf_font()

    title_style = ParagraphStyle("Title", fontName=font_name, fontSize=18, leading=24, alignment=TA_LEFT)
    body_style = ParagraphStyle("Body", fontName=font_name, fontSize=11, leading=17)
    question_style = ParagraphStyle("Question", fontName=font_name, fontSize=11, leading=17, spaceBefore=10)
    answer_style = ParagraphStyle("Answer", fontName=font_name, fontSize=11, leading=17, spaceAfter=4)

    story = [
        Paragraph(_pdf_escape(title), title_style),
        HRFlowable(width="100%", thickness=1, color="#333333", spaceBefore=4, spaceAfter=10),
        Paragraph(_pdf_escape(summary), body_style),
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=1, color="#333333", spaceBefore=4, spaceAfter=10),
    ]
    if not qa_pairs:
        story.append(Paragraph("내보낼 대화 내용이 없습니다.", body_style))
    for index, pair in enumerate(qa_pairs, start=1):
        story.append(Paragraph(f"질문 {index}. " + _pdf_escape(pair["question"]), question_style))
        story.append(Paragraph(f"답변 {index}. " + _pdf_escape(pair["answer"]), answer_style))
        if index != len(qa_pairs):
            story.append(HRFlowable(width="100%", thickness=0.5, color="#999999", spaceBefore=6, spaceAfter=6))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )
    doc.build(story)
    return buffer.getvalue()

def _common_prefix_length(a: str, b: str) -> int:
    length = min(len(a), len(b))
    for i in range(length):
        if a[i] != b[i]:
            return i
    return length


def stream_answer(question: str, evidence: List[Dict], history: Optional[List[Dict[str, str]]] = None) -> Iterator[str]:
    """Yields answer deltas from CLOVA Studio; does not expose provider events to the browser."""
    if not evidence:
        yield "분석이 완료된 영상 자막에서 질문과 연결되는 근거를 찾지 못했습니다. 먼저 영상을 분석해 주세요."
        return
    if config.CHAT_PROVIDER == "mock":
        text = "로컬 테스트 모드입니다. 아래 근거 구간을 기준으로 CLOVA Chat 답변을 생성하게 됩니다."
        for word in text.split(" "):
            yield word + " "
        return
    if config.CHAT_PROVIDER != "clova":
        raise RuntimeError("CHAT_PROVIDER must be mock or clova")
    if not config.CLOVASTUDIO_API_KEY:
        raise RuntimeError("CLOVASTUDIO_API_KEY is required for CHAT_PROVIDER=clova")

    previous_content = ""
    with httpx.stream(
        "POST",
        "https://clovastudio.stream.ntruss.com/v3/chat-completions/" + config.CLOVA_MODEL,
        headers=_chat_headers(stream=True),
        json=_chat_payload(question, evidence, history),
        timeout=90,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                return
            event = json.loads(raw)
            content = event.get("message", {}).get("content")
            if not content:
                continue
            delta = content[_common_prefix_length(previous_content, content):]
            previous_content = content
            if delta:
                yield delta
