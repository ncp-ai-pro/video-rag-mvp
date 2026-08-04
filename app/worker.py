"""Run this separately from FastAPI: python -m app.worker."""
import json
import subprocess
import time
from pathlib import Path

from . import config
from .db import connection, initialize
from .services import (
    ANALYSIS_MESSAGES,
    collect_channel_metadata,
    finish_analysis,
    import_transcript,
    update_analysis_progress,
    upsert_video,
)


def claim_job():
    with connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
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


def analyze_video(job_id: int, video_id: int):
    """Downloads only a selected video's subtitles. STT wiring is intentionally guarded by env vars."""
    with connection() as conn:
        video = conn.execute("SELECT url FROM videos WHERE id=?", (video_id,)).fetchone()
    if not video:
        raise RuntimeError("video not found")
    output_dir = config.DATA_DIR / "downloads" / str(video_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            config.YTDLP_BIN,
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "ko.*,en.*",
            "--sub-format",
            "vtt",
            "-o",
            str(output_dir / "source.%(ext)s"),
            video["url"],
        ],
        check=True,
        timeout=300,
    )
    vtt_files = list(output_dir.glob("*.vtt"))
    if not vtt_files:
        update_analysis_progress(job_id, video_id, "transcribing")
        raise RuntimeError(
            "subtitle_not_found: CLOVA Speech long-audio integration is the next production adapter; "
            "configure CLOVA_SPEECH_INVOKE_URL and CLOVA_SPEECH_API_KEY before enabling it"
        )
    segments = parse_vtt(vtt_files[0])
    if not segments:
        raise RuntimeError("subtitle_parse_failed")
    update_analysis_progress(job_id, video_id, "chunking")
    update_analysis_progress(job_id, video_id, "embedding")
    import_transcript(video_id, segments, mark_analyzed=False)


def parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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
        content = " ".join(text)
        if content:
            segments.append({"start_seconds": parse_timestamp(start), "end_seconds": parse_timestamp(end), "text": content})
        index += 1
    return segments


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
