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

import httpx

from . import config
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


def collect_channel_metadata(url: str) -> List[Dict]:
    """Fetches playlist entries only; --flat-playlist never downloads media."""
    result = subprocess.run(
        [config.YTDLP_BIN, "--flat-playlist", "--dump-json", "--skip-download", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    videos = []
    for line in result.stdout.splitlines():
        item = json.loads(line)
        video_id = item.get("id")
        if not video_id:
            continue
        videos.append(
            {
                "platform_video_id": video_id,
                "title": item.get("title") or video_id,
                "description": item.get("description") or "",
                "url": item.get("webpage_url") or "https://www.youtube.com/watch?v=" + video_id,
                "thumbnail_url": item.get("thumbnail"),
                "duration_seconds": item.get("duration"),
                "uploaded_at": item.get("upload_date"),
            }
        )
    return videos


def import_transcript(
    video_id: int,
    segments: List[Dict],
    *,
    mark_analyzed: bool = True,
    embed_text: Callable[[str], List[float]] = embedding,
):
    with connection() as conn:
        exists = conn.execute("SELECT id FROM videos WHERE id=?", (video_id,)).fetchone()
        if not exists:
            raise LookupError("video not found")
        conn.execute("DELETE FROM transcript_chunks WHERE video_id=?", (video_id,))
        for segment in segments:
            if segment["end_seconds"] <= segment["start_seconds"]:
                raise ValueError("end_seconds must be greater than start_seconds")
            conn.execute(
                """
                INSERT INTO transcript_chunks(video_id, start_seconds, end_seconds, text, embedding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    video_id,
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


def find_evidence(user_id: int, query: str, limit: int, video_id: Optional[int] = None) -> List[Dict]:
    query_vector = embedding(query)
    video_filter = " AND videos.id=?" if video_id is not None else ""
    video_params = (video_id,) if video_id is not None else ()
    with connection() as conn:
        if is_postgres():
            rows = conn.execute(
                """
                SELECT chunks.start_seconds, chunks.end_seconds, chunks.text,
                       videos.id AS video_id, videos.title, videos.url,
                       1 - (chunks.embedding <=> ?::vector) AS score
                FROM transcript_chunks AS chunks
                JOIN videos ON videos.id = chunks.video_id
                JOIN channels ON channels.id = videos.channel_id
                WHERE videos.analysis_status IN ('succeeded', 'ready') AND channels.user_id=?"""
                + video_filter
                + """
                ORDER BY chunks.embedding <=> ?::vector
                LIMIT ?
                """,
                (json.dumps(query_vector), user_id, *video_params, json.dumps(query_vector), limit),
            ).fetchall()
            evidence = []
            for row in rows:
                separator = "&" if "?" in row["url"] else "?"
                evidence.append(
                    {
                        "video_id": row["video_id"],
                        "title": row["title"],
                        "start_seconds": row["start_seconds"],
                        "end_seconds": row["end_seconds"],
                        "quote": row["text"],
                        "url": row["url"] + separator + "t=" + str(int(row["start_seconds"])) + "s",
                        "score": round(float(row["score"]), 4),
                    }
                )
            return evidence
        rows = conn.execute(
            """
            SELECT chunks.start_seconds, chunks.end_seconds, chunks.text, chunks.embedding,
                   videos.id AS video_id, videos.title, videos.url
            FROM transcript_chunks AS chunks
            JOIN videos ON videos.id = chunks.video_id
            JOIN channels ON channels.id = videos.channel_id
            WHERE videos.analysis_status IN ('succeeded', 'ready') AND channels.user_id=?"""
            + video_filter
            + """
            """,
            (user_id, *video_params),
        ).fetchall()
    evidence = []
    for row in rows:
        separator = "&" if "?" in row["url"] else "?"
        evidence.append(
            {
                "video_id": row["video_id"],
                "title": row["title"],
                "start_seconds": row["start_seconds"],
                "end_seconds": row["end_seconds"],
                "quote": row["text"],
                "url": row["url"] + separator + "t=" + str(int(row["start_seconds"])) + "s",
                "score": round(cosine(query_vector, json.loads(row["embedding"])), 4),
            }
        )
    return sorted(evidence, key=lambda item: item["score"], reverse=True)[:limit]


def record_chat_message(user_id: int, role: str, content: str) -> None:
    """Appends a turn and prunes the workspace's history to the configured retention window."""
    keep = max(0, config.CHAT_HISTORY_TURNS) * 2
    with connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages(user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.execute(
            """
            DELETE FROM chat_messages
            WHERE user_id=? AND id NOT IN (
                SELECT id FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT ?
            )
            """,
            (user_id, user_id, keep),
        )


def recent_chat_history(user_id: int) -> List[Dict[str, str]]:
    """Returns this workspace's last CHAT_HISTORY_TURNS turns in chronological order."""
    limit = max(0, config.CHAT_HISTORY_TURNS) * 2
    if limit == 0:
        return []
    with connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def _chat_instruction(evidence: List[Dict]) -> str:
    context = "\n\n".join(
        "[{} {}-{}]\n{}".format(item["title"], item["start_seconds"], item["end_seconds"], item["quote"])
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
            delta = content[len(previous_content) :] if content.startswith(previous_content) else content
            previous_content = content
            if delta:
                yield delta
