"""Run this separately from FastAPI: python -m app.worker."""
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from . import config
from .db import connection, initialize, is_postgres
from .services import (
    ANALYSIS_MESSAGES,
    EmbeddingRateLimiter,
    collect_channel_metadata,
    finish_analysis,
    import_transcript,
    normalize_clova_speech_segments,
    object_storage_is_configured,
    record_analysis_artifact,
    transcribe_object_storage,
    update_analysis_progress,
    upload_artifact_file,
    upload_artifact_json,
    upsert_video,
)


NO_SUBTITLE_MARKERS = (
    "there are no subtitles for the requested languages",
    "no subtitles available",
    "requested subtitles are not available",
)

WORKER_EMBEDDING_LIMITER = EmbeddingRateLimiter(
    min_interval_seconds=config.WORKER_EMBEDDING_MIN_INTERVAL_SECONDS,
    max_retries=config.WORKER_EMBEDDING_MAX_RETRIES,
    backoff_base_seconds=config.WORKER_EMBEDDING_BACKOFF_BASE_SECONDS,
)


def yt_dlp_failure_message(result: subprocess.CompletedProcess) -> str:
    """Returns the last useful yt-dlp error line without exposing a full command output."""
    output = "\n".join(part for part in (result.stderr, result.stdout) if part)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    error_lines = [line for line in lines if "error:" in line.lower()]
    return (error_lines or lines or ["yt-dlp exited without an error message"])[-1][:500]


def subtitles_are_unavailable(result: subprocess.CompletedProcess) -> bool:
    output = "\n".join(part for part in (result.stderr, result.stdout) if part).lower()
    return any(marker in output for marker in NO_SUBTITLE_MARKERS)


def download_subtitles(video_url: str, output_dir: Path) -> Optional[Path]:
    """Returns a VTT file, None only when captions do not exist, or raises on extraction failure."""
    result = subprocess.run(
        [
            config.YTDLP_BIN,
            "--no-playlist",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "ko.*,en.*",
            "--sub-format",
            "vtt",
            "--retries",
            "3",
            "--extractor-retries",
            "3",
            "--no-progress",
            "-o",
            str(output_dir / "source.%(ext)s"),
            video_url,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    vtt_files = sorted(output_dir.glob("*.vtt"), key=lambda path: path.stat().st_mtime, reverse=True)
    if vtt_files:
        return vtt_files[0]
    if result.returncode and not subtitles_are_unavailable(result):
        raise RuntimeError("subtitle_download_failed: " + yt_dlp_failure_message(result))
    return None


def claim_job():
    with connection() as conn:
        query = "SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1"
        if is_postgres():
            query += " FOR UPDATE SKIP LOCKED"
        row = conn.execute(query).fetchone()
        if not row:
            return None
        if row["kind"] == "analyze_video":
            conn.execute(
                """
                UPDATE jobs
                SET status='running', progress_stage='downloading_caption', progress_message=?,
                    attempts=attempts+1, started_at=CURRENT_TIMESTAMP,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (ANALYSIS_MESSAGES["downloading_caption"], row["id"]),
            )
            conn.execute(
                """
                UPDATE videos
                SET analysis_status='running', analysis_stage='downloading_caption', analysis_message=?,
                    analysis_error=NULL, analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (ANALYSIS_MESSAGES["downloading_caption"], row["resource_id"]),
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET status='running', attempts=attempts+1, started_at=CURRENT_TIMESTAMP,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (row["id"],),
            )
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())


def finish_scan(job_id: int, error: str = None):
    with connection() as conn:
        if error:
            conn.execute(
                """
                UPDATE jobs
                SET status='failed', error_message=?, progress_stage='failed', progress_message=?,
                    finished_at=CURRENT_TIMESTAMP, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (error[:2000], error[:2000], job_id),
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET status='succeeded', progress_stage='completed', progress_message='작업이 완료되었습니다.',
                    finished_at=CURRENT_TIMESTAMP, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (job_id,),
            )


def scan_channel(channel_id: int):
    with connection() as conn:
        channel = conn.execute("SELECT url FROM channels WHERE id=?", (channel_id,)).fetchone()
    if not channel:
        raise RuntimeError("channel not found")
    for video in collect_channel_metadata(channel["url"]):
        upsert_video(channel_id, video)
    with connection() as conn:
        conn.execute("UPDATE channels SET last_scanned_at=CURRENT_TIMESTAMP WHERE id=?", (channel_id,))


def artifact_key(video_id: int, job_id: int, name: str) -> str:
    return f"{config.OBJECT_STORAGE_ARTIFACT_PREFIX}/{video_id}/revisions/{job_id}/{name}"


def stt_input_key(video_id: int, job_id: int, suffix: str) -> str:
    return f"{config.OBJECT_STORAGE_STT_INPUT_PREFIX}/videos/{video_id}/revisions/{job_id}/source{suffix}"


def stt_result_key(video_id: int, job_id: int) -> str:
    return f"{config.OBJECT_STORAGE_STT_RESULT_PREFIX}/videos/{video_id}/revisions/{job_id}/result.raw.json"


def store_normalized_transcript(video_id: int, job_id: int, source: str, segments):
    if not object_storage_is_configured():
        return None
    object_key = upload_artifact_json(
        {
            "version": 1,
            "video_id": video_id,
            "job_id": job_id,
            "source": source,
            "segments": segments,
        },
        artifact_key(video_id, job_id, "transcript.normalized.v1.json"),
    )
    record_analysis_artifact(video_id, job_id, "normalized_transcript", object_key, "application/json")
    return object_key


def download_audio(video_url: str, output_dir: Path) -> Path:
    """Downloads and transcodes a selected video to an STT-supported M4A artifact."""
    output_template = output_dir / "source.%(ext)s"
    result = subprocess.run(
        [
            config.YTDLP_BIN,
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "m4a",
            "--audio-quality",
            "5",
            "--retries",
            "3",
            "--extractor-retries",
            "3",
            "--no-progress",
            "-o",
            str(output_template),
            video_url,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode:
        raise RuntimeError("audio_download_failed: " + yt_dlp_failure_message(result))
    files = sorted(output_dir.glob("source.*"), key=lambda path: path.stat().st_mtime, reverse=True)
    audio = next((path for path in files if path.suffix.lower() == ".m4a"), None)
    if not audio:
        raise RuntimeError("audio_download_failed: yt-dlp did not produce an m4a file")
    return audio


def analyze_video(job_id: int, video_id: int):
    """Prefers YouTube subtitles; falls back to Object Storage-backed CLOVA Speech STT."""
    with connection() as conn:
        video = conn.execute("SELECT url FROM videos WHERE id=?", (video_id,)).fetchone()
    if not video:
        raise RuntimeError("video not found")
    output_dir = config.DATA_DIR / "downloads" / str(video_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    vtt_path = download_subtitles(video["url"], output_dir)
    if vtt_path:
        segments = parse_vtt(vtt_path)
        if not segments:
            raise RuntimeError("subtitle_parse_failed")
        if object_storage_is_configured():
            object_key = upload_artifact_file(
                vtt_path, artifact_key(video_id, job_id, "source.vtt"), "text/vtt; charset=utf-8"
            )
            record_analysis_artifact(video_id, job_id, "source_vtt", object_key, "text/vtt")
        store_normalized_transcript(video_id, job_id, "youtube_subtitle", segments)
    else:
        update_analysis_progress(job_id, video_id, "transcribing")
        if not object_storage_is_configured():
            raise RuntimeError(
                "subtitle_not_found: configure Object Storage and CLOVA Speech before analyzing videos without captions"
            )
        audio_path = download_audio(video["url"], output_dir)
        audio_key = stt_input_key(video_id, job_id, audio_path.suffix.lower())
        upload_artifact_file(audio_path, audio_key, "audio/mp4")
        record_analysis_artifact(video_id, job_id, "source_audio", audio_key, "audio/mp4")
        speech_payload = transcribe_object_storage(audio_key)
        result_key = upload_artifact_json(speech_payload, stt_result_key(video_id, job_id))
        record_analysis_artifact(video_id, job_id, "speech_raw_result", result_key, "application/json")
        segments = normalize_clova_speech_segments(speech_payload)
        store_normalized_transcript(video_id, job_id, "clova_speech", segments)
    update_analysis_progress(job_id, video_id, "chunking")
    chunks = build_rag_chunks(segments)
    if not chunks:
        raise RuntimeError("chunking_failed: no searchable transcript chunks")
    update_analysis_progress(job_id, video_id, "embedding")
    import_transcript(video_id, chunks, mark_analyzed=False, embed_text=WORKER_EMBEDDING_LIMITER.embed)


def parse_timestamp(value: str) -> float:
    timestamp = value.strip().split(maxsplit=1)[0]
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_vtt_text(value: str) -> str:
    """Removes YouTube VTT timing/style markup before embedding transcript text."""
    without_tags = re.sub(r"<[^>]+>", "", value)
    return " ".join(without_tags.split())


def parse_vtt(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    segments, index = [], 0
    while index < len(lines):
        if "-->" not in lines[index]:
            index += 1
            continue
        start, end = [part.strip() for part in lines[index].split("-->")]
        index += 1
        text = []
        while index < len(lines) and lines[index].strip():
            text.append(lines[index].strip())
            index += 1
        content = clean_vtt_text(" ".join(text))
        if content:
            segments.append({"start_seconds": parse_timestamp(start), "end_seconds": parse_timestamp(end), "text": content})
        index += 1
    return segments


def _caption_delta(previous: str, current: str) -> str:
    """Drops repeated text from YouTube's rolling automatic-caption cues."""
    if not previous or current.startswith(previous):
        return current[len(previous) :].strip()
    if current in previous:
        return ""
    max_overlap = min(len(previous), len(current))
    for overlap in range(max_overlap, 0, -1):
        if previous.endswith(current[:overlap]):
            return current[overlap:].strip()
    return current


def build_rag_chunks(segments):
    """Merges subtitle cues into bounded, non-duplicated RAG documents for embedding."""
    chunks = []
    current_text, current_start, current_end = [], None, None
    previous_caption = ""

    for segment in segments:
        text = " ".join(str(segment.get("text") or "").split())
        try:
            start = float(segment["start_seconds"])
            end = float(segment["end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if not text or end <= start:
            continue

        delta = _caption_delta(previous_caption, text)
        if len(text) >= len(previous_caption) or not previous_caption.endswith(text):
            previous_caption = text
        if not delta:
            continue

        candidate_text = " ".join(current_text + [delta])
        exceeds_duration = current_start is not None and end - current_start > config.WORKER_RAG_CHUNK_MAX_SECONDS
        exceeds_size = current_text and len(candidate_text) > config.WORKER_RAG_CHUNK_MAX_CHARS
        if exceeds_duration or exceeds_size:
            chunks.append(
                {"start_seconds": current_start, "end_seconds": current_end, "text": " ".join(current_text)}
            )
            current_text, current_start = [], None

        if current_start is None:
            current_start = start
        current_end = end
        current_text.append(delta)

    if current_text and current_start is not None and current_end is not None:
        chunks.append({"start_seconds": current_start, "end_seconds": current_end, "text": " ".join(current_text)})
    return chunks


def run_once():
    job = claim_job()
    if not job:
        return False
    try:
        if job["kind"] == "scan_channel":
            scan_channel(job["resource_id"])
            finish_scan(job["id"])
        else:
            analyze_video(job["id"], job["resource_id"])
            finish_analysis(job["id"], job["resource_id"])
    except Exception as exc:
        if job["kind"] == "analyze_video":
            finish_analysis(job["id"], job["resource_id"], str(exc))
        else:
            finish_scan(job["id"], str(exc))
    return True


if __name__ == "__main__":
    initialize()
    while True:
        if not run_once():
            time.sleep(2)
