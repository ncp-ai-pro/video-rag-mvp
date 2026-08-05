import asyncio
import json
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from .config import CHAT_PUBLIC_ORIGIN
from .db import connection, is_postgres, is_unique_violation
from .dependencies import current_workspace
from .schemas import ChannelCreate, SearchRequest, TranscriptImport, VideoCreate, WorkspaceConnect
from .services import (
    analysis_event_state,
    enqueue,
    enqueue_analysis as enqueue_analysis_job,
    find_metadata,
    import_transcript,
    upsert_video,
)
from .workspaces import create_guest_workspace, create_session, find_workspace
from .web import create_web_app


app = create_web_app(title="Video RAG API", version="0.2.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
SSE_POLL_INTERVAL_SECONDS = 1
SSE_HEARTBEAT_SECONDS = 20


def required_channel(channel_id: int, user_id: int):
    with connection() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id=? AND user_id=?", (channel_id, user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="channel not found")
    return dict(row)


def required_video(video_id: int, user_id: int):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT videos.* FROM videos JOIN channels ON channels.id=videos.channel_id
            WHERE videos.id=? AND channels.user_id=?
            """,
            (video_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="video not found")
    return dict(row)


@app.get("/health")
def health():
    if is_postgres():
        return {"status": "ok", "queue": "postgresql jobs table", "mode": "postgresql"}
    return {"status": "ok", "queue": "sqlite job table", "mode": "sqlite"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/runtime-config.js", include_in_schema=False)
def runtime_config():
    body = "window.VIDEO_RAG_CHAT_ORIGIN = " + json.dumps(CHAT_PUBLIC_ORIGIN) + ";\n"
    return Response(body, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/auth/me")
def auth_me(request: Request):
    return current_workspace(request)


@app.post("/auth/workspace")
def connect_workspace(payload: WorkspaceConnect, request: Request):
    workspace = find_workspace(payload.workspace_code)
    if not workspace:
        raise HTTPException(status_code=404, detail="작업공간 코드를 찾지 못했습니다.")
    request.state.workspace = workspace
    request.state.new_session_token = create_session(workspace["id"])
    return workspace


@app.post("/auth/new-workspace", status_code=status.HTTP_201_CREATED)
def new_workspace(request: Request):
    workspace = create_guest_workspace()
    request.state.workspace = workspace
    request.state.new_session_token = create_session(workspace["id"])
    return workspace


@app.post("/channels", status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelCreate, request: Request):
    workspace = current_workspace(request)
    with connection() as conn:
        try:
            row = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING *",
                (workspace["id"], str(payload.url), payload.name),
            ).fetchone()
        except Exception as exc:
            if is_unique_violation(exc):
                raise HTTPException(status_code=409, detail="channel already exists in this workspace")
            raise
    return dict(row)


@app.get("/channels")
def list_channels(request: Request):
    workspace = current_workspace(request)
    with connection() as conn:
        rows = conn.execute("SELECT * FROM channels WHERE user_id=? ORDER BY id DESC", (workspace["id"],)).fetchall()
    return [dict(row) for row in rows]


@app.get("/channels/{channel_id}/videos")
def list_channel_videos(channel_id: int, request: Request):
    workspace = current_workspace(request)
    required_channel(channel_id, workspace["id"])
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, platform_video_id, title, description, url, thumbnail_url, duration_seconds,
                   uploaded_at, analysis_status, analysis_stage, analysis_message, analysis_error,
                   analysis_updated_at
            FROM videos WHERE channel_id=? ORDER BY uploaded_at DESC, id DESC
            """,
            (channel_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/channels/{channel_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def enqueue_channel_scan(channel_id: int, request: Request):
    workspace = current_workspace(request)
    required_channel(channel_id, workspace["id"])
    return {"job_id": enqueue("scan_channel", channel_id), "status": "queued"}


@app.post("/channels/{channel_id}/videos", status_code=status.HTTP_201_CREATED)
def create_video_for_local_test(channel_id: int, payload: VideoCreate, request: Request):
    workspace = current_workspace(request)
    required_channel(channel_id, workspace["id"])
    return {"video_id": upsert_video(channel_id, payload.model_dump())}


@app.get("/videos/{video_id}")
def get_video(video_id: int, request: Request):
    workspace = current_workspace(request)
    return required_video(video_id, workspace["id"])


@app.post("/videos/{video_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def enqueue_analysis(video_id: int, request: Request):
    workspace = current_workspace(request)
    video = required_video(video_id, workspace["id"])
    if video["analysis_status"] in ("queued", "running"):
        raise HTTPException(status_code=409, detail="video analysis is already in progress")
    if video["analysis_status"] in ("ready", "succeeded"):
        raise HTTPException(status_code=409, detail="video is already analyzed")
    return {"job_id": enqueue_analysis_job(video_id), "status": "queued"}


@app.get("/videos/{video_id}/events")
async def analysis_events(video_id: int, request: Request):
    """Streams DB-owned analysis state; Worker never calls this API."""
    workspace = current_workspace(request)
    await asyncio.to_thread(required_video, video_id, workspace["id"])
    initial_state = await asyncio.to_thread(analysis_event_state, video_id, workspace["id"])
    if initial_state is None:
        raise HTTPException(status_code=404, detail="analysis job not found")

    async def event_stream():
        last_payload = None
        last_heartbeat = time.monotonic()
        yield "retry: 3000\n\n"
        while True:
            state = await asyncio.to_thread(analysis_event_state, video_id, workspace["id"])
            if state is None:
                return
            payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            if payload != last_payload:
                yield "event: analysis_status\ndata: " + payload + "\n\n"
                last_payload = payload
                if state["status"] in ("succeeded", "failed"):
                    return
            if time.monotonic() - last_heartbeat >= SSE_HEARTBEAT_SECONDS:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/videos/{video_id}/transcript", status_code=status.HTTP_204_NO_CONTENT)
def import_local_transcript(video_id: int, payload: TranscriptImport, request: Request):
    workspace = current_workspace(request)
    required_video(video_id, workspace["id"])
    try:
        import_transcript(video_id, [segment.model_dump() for segment in payload.segments])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/recommendations")
def recommendations(payload: SearchRequest, request: Request):
    workspace = current_workspace(request)
    return {
        "query": payload.query,
        "items": find_metadata(workspace["id"], payload.query, payload.limit),
        "notice": "추천은 제목과 영상 설명의 embedding 유사도 기반이며 영상 내용을 검증하지 않습니다.",
    }
