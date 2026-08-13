"""Run this separately from FastAPI: python -m app.worker."""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from . import config
from .analysis_queue import queue_arguments, queue_name
from .db import connection, initialize, is_postgres
from .services import (
    ANALYSIS_MESSAGES,
    EmbeddingRateLimiter,
    collect_channel_metadata,
    finish_analysis,
    has_video_embedding,
    import_transcript,
    is_youtube_rate_limited_error,
    normalize_clova_speech_segments,
    object_storage_is_configured,
    publish_pending_outbox,
    record_analysis_artifact,
    schedule_job_retry,
    transcribe_object_storage,
    update_analysis_progress,
    upload_artifact_file,
    upload_artifact_json,
    upsert_video,
    yt_dlp_throttle_args,
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
            *yt_dlp_throttle_args(),
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


def _mark_job_running(conn, row):
    worker_id = f"{os.uname().nodename}:{os.getpid()}"
    if row["kind"] == "analyze_video":
        conn.execute(
            """
            UPDATE jobs
            SET status='running', progress_stage='downloading_caption', progress_message=?,
                attempts=attempts+1, started_at=CURRENT_TIMESTAMP, locked_at=CURRENT_TIMESTAMP,
                locked_by=?, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (ANALYSIS_MESSAGES["downloading_caption"], worker_id, row["id"]),
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
                locked_at=CURRENT_TIMESTAMP, locked_by=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id=?
            """,
            (worker_id, row["id"]),
        )


def claim_job():
    with connection() as conn:
        query = """
            SELECT * FROM jobs
            WHERE status='queued' AND (next_run_at IS NULL OR next_run_at <= CURRENT_TIMESTAMP)
            ORDER BY priority ASC, id ASC
            LIMIT 1
        """
        if is_postgres():
            query += " FOR UPDATE SKIP LOCKED"
        row = conn.execute(query).fetchone()
        if not row:
            return None
        _mark_job_running(conn, row)
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())


def claim_job_by_id(job_id: int):
    with connection() as conn:
        query = """
            SELECT * FROM jobs
            WHERE id=? AND status='queued'
              AND (next_run_at IS NULL OR next_run_at <= CURRENT_TIMESTAMP)
        """
        if is_postgres():
            query += " FOR UPDATE SKIP LOCKED"
        row = conn.execute(query, (job_id,)).fetchone()
        if not row:
            return None
        _mark_job_running(conn, row)
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
            *yt_dlp_throttle_args(),
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
    if has_video_embedding(video_id):
        return
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
    paragraphs, chunks = build_rag_documents(segments)
    if not chunks:
        raise RuntimeError("chunking_failed: no searchable transcript chunks")
    update_analysis_progress(job_id, video_id, "embedding")
    import_transcript(
        video_id,
        chunks,
        paragraphs=paragraphs,
        mark_analyzed=False,
        embed_text=WORKER_EMBEDDING_LIMITER.embed,
    )


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


def _normalized_caption_units(segments):
    units = []
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
        units.append({"start_seconds": start, "end_seconds": end, "text": delta})
    return units


def _looks_like_sentence_end(text: str) -> bool:
    return bool(re.search(r"([.!?。！？]|(다|요|죠|니다|습니다|네요|거예요|겁니다))\s*$", text))


def _merge_caption_units(units, *, max_seconds: float, max_chars: int, paragraph_mode: bool = False):
    groups = []
    current_text, current_start, current_end = [], None, None
    current_units = []

    def flush():
        nonlocal current_text, current_start, current_end, current_units
        if current_text and current_start is not None and current_end is not None:
            groups.append(
                {
                    "start_seconds": current_start,
                    "end_seconds": current_end,
                    "text": " ".join(current_text),
                    "units": current_units,
                }
            )
        current_text, current_start, current_end, current_units = [], None, None, []

    for index, unit in enumerate(units):
        delta = unit["text"]
        start = unit["start_seconds"]
        end = unit["end_seconds"]
        candidate_text = " ".join(current_text + [delta])
        exceeds_duration = current_start is not None and end - current_start > max_seconds
        exceeds_size = current_text and len(candidate_text) > max_chars
        if exceeds_duration or exceeds_size:
            flush()

        if current_start is None:
            current_start = start
        current_end = end
        current_text.append(delta)
        current_units.append(unit)

        if paragraph_mode:
            next_start = units[index + 1]["start_seconds"] if index + 1 < len(units) else None
            pause = next_start - end if next_start is not None else 0
            long_enough = current_start is not None and end - current_start >= 10
            if long_enough and _looks_like_sentence_end(" ".join(current_text)) and pause >= 0.6:
                flush()

    flush()
    return groups


def build_rag_documents(segments):
    """Builds paragraph groups for context and smaller chunks for vector search."""
    units = _normalized_caption_units(segments)
    paragraphs = _merge_caption_units(
        units,
        max_seconds=config.WORKER_PARAGRAPH_MAX_SECONDS,
        max_chars=config.WORKER_PARAGRAPH_MAX_CHARS,
        paragraph_mode=True,
    )
    chunks = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        paragraph["paragraph_index"] = paragraph_index
        for chunk_index, chunk in enumerate(
            _merge_caption_units(
                paragraph["units"],
                max_seconds=config.WORKER_RAG_CHUNK_MAX_SECONDS,
                max_chars=config.WORKER_RAG_CHUNK_MAX_CHARS,
            )
        ):
            chunks.append(
                {
                    "paragraph_index": paragraph_index,
                    "chunk_index": chunk_index,
                    "start_seconds": chunk["start_seconds"],
                    "end_seconds": chunk["end_seconds"],
                    "text": chunk["text"],
                }
            )
        paragraph.pop("units", None)
    return paragraphs, chunks


def build_rag_chunks(segments):
    """Backward-compatible helper for tests and manual checks."""
    return [
        {"start_seconds": chunk["start_seconds"], "end_seconds": chunk["end_seconds"], "text": chunk["text"]}
        for chunk in build_rag_documents(segments)[1]
    ]


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
        if is_youtube_rate_limited_error(str(exc)) and schedule_job_retry(job, str(exc)):
            return True
        if job["kind"] == "analyze_video":
            finish_analysis(job["id"], job["resource_id"], str(exc))
        else:
            finish_scan(job["id"], str(exc))
    return True


def _run_claimed_job(job) -> bool:
    try:
        if job["kind"] == "scan_channel":
            scan_channel(job["resource_id"])
            finish_scan(job["id"])
        else:
            analyze_video(job["id"], job["resource_id"])
            finish_analysis(job["id"], job["resource_id"])
    except Exception as exc:
        if is_youtube_rate_limited_error(str(exc)) and schedule_job_retry(job, str(exc)):
            return True
        if job["kind"] == "analyze_video":
            finish_analysis(job["id"], job["resource_id"], str(exc))
        else:
            finish_scan(job["id"], str(exc))
    return True


def consume_rabbitmq():
    try:
        import pika
    except ImportError as exc:
        raise RuntimeError("pika is required when WORKER_QUEUE_MODE=rabbitmq") from exc
    if not config.RABBITMQ_URL:
        raise RuntimeError("RABBITMQ_URL is required when WORKER_QUEUE_MODE=rabbitmq")

    connection_params = pika.URLParameters(config.RABBITMQ_URL)
    rabbit = pika.BlockingConnection(connection_params)
    channel = rabbit.channel()
    name = queue_name()
    channel.queue_declare(queue=name, durable=True, arguments=queue_arguments())
    channel.basic_qos(prefetch_count=config.WORKER_PREFETCH_COUNT)

    def republish_due_jobs():
        while True:
            try:
                publish_pending_outbox()
            except Exception as exc:
                print(f"outbox_publish_failed: {exc}", flush=True)
            time.sleep(config.WORKER_OUTBOX_PUBLISH_INTERVAL_SECONDS)

    threading.Thread(target=republish_due_jobs, daemon=True).start()

    def on_message(ch, method, properties, body):
        try:
            payload = json.loads(body.decode("utf-8"))
            job = claim_job_by_id(int(payload["job_id"]))
            if job:
                _run_claimed_job(job)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=name, on_message_callback=on_message)
    channel.start_consuming()


if __name__ == "__main__":
    initialize()
    if config.WORKER_QUEUE_MODE == "rabbitmq":
        consume_rabbitmq()
    while True:
        if not run_once():
            time.sleep(2)
