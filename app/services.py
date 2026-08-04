import hashlib
import json
import math
import re
import subprocess
import uuid
from typing import Dict, Iterable, List, Optional

import httpx

from . import config
from .db import connection


ANALYSIS_MESSAGES = {
    "queued": "분석 작업을 기다리고 있습니다.",
    "downloading_caption": "자막을 수집하고 있습니다.",
    "transcribing": "자막이 없어 음성을 텍스트로 변환하고 있습니다.",
    "chunking": "자막을 검색 가능한 구간으로 나누고 있습니다.",
    "embedding": "자막 구간의 embedding을 생성하고 있습니다.",
    "completed": "분석이 완료되었습니다. 이제 질문할 수 있습니다.",
    "failed": "분석에 실패했습니다.",
}


def metadata_text(video: Dict) -> str:
    return "\n".join(part for part in [video["title"], video.get("description", "")] if part).strip()


def _tokens(text: str) -> Iterable[str]:
    return re.findall(r"[\w가-힣]{2,}", text.lower())


def _mock_embedding(text: str, dimensions: int = 128) -> List[float]:
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
    if updated_at and "T" not in updated_at:
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


def import_transcript(video_id: int, segments: List[Dict], *, mark_analyzed: bool = True):
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
                    json.dumps(embedding(segment["text"])),
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


def find_evidence(user_id: int, query: str, limit: int) -> List[Dict]:
    query_vector = embedding(query)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT chunks.start_seconds, chunks.end_seconds, chunks.text, chunks.embedding,
                   videos.id AS video_id, videos.title, videos.url
            FROM transcript_chunks AS chunks
            JOIN videos ON videos.id = chunks.video_id
            JOIN channels ON channels.id = videos.channel_id
            WHERE videos.analysis_status IN ('succeeded', 'ready') AND channels.user_id=?
            """,
            (user_id,),
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


def answer(question: str, evidence: List[Dict]) -> str:
    if not evidence:
        return "분석이 완료된 영상 자막에서 질문과 연결되는 근거를 찾지 못했습니다. 먼저 영상을 분석해 주세요."
    if config.CHAT_PROVIDER == "mock":
        return "로컬 테스트 모드입니다. 아래 근거 구간을 기준으로 CLOVA Chat 답변을 생성하게 됩니다."
    if config.CHAT_PROVIDER != "clova":
        raise RuntimeError("CHAT_PROVIDER must be mock or clova")
    if not config.CLOVASTUDIO_API_KEY:
        raise RuntimeError("CLOVASTUDIO_API_KEY is required for CHAT_PROVIDER=clova")
    context = "\n\n".join(
        "[{} {}-{}]\n{}".format(item["title"], item["start_seconds"], item["end_seconds"], item["quote"])
        for item in evidence
    )
    instruction = (
        "주어진 영상 자막 근거만 사용해 한국어로 답하세요. 근거에 없는 사실은 모른다고 말하세요. "
        "시간 표시는 API가 별도로 반환하므로 본문에 임의의 시간을 만들지 마세요.\n\n근거:\n" + context
    )
    response = httpx.post(
        "https://clovastudio.stream.ntruss.com/v3/chat-completions/" + config.CLOVA_MODEL,
        headers={
            "Authorization": "Bearer " + config.CLOVASTUDIO_API_KEY,
            "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        },
        json={
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": question},
            ],
            "maxTokens": 500,
            "temperature": 0.2,
            "topP": 0.8,
            "topK": 0,
            "repetitionPenalty": 1.1,
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["result"]["message"]["content"]
