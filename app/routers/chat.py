import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..dependencies import current_workspace
from ..schemas import ChatRequest
from ..services import (
    answer,
    find_evidence,
    paged_chat_history,
    record_chat_message,
    recent_chat_history,
    stream_answer,
    video_belongs_to_workspace,
)


router = APIRouter()


def _verified_video_id(workspace_id: int, video_id: Optional[int]) -> Optional[int]:
    if video_id is None:
        return None
    if not video_belongs_to_workspace(workspace_id, video_id):
        raise HTTPException(status_code=404, detail="video not found")
    return video_id


@router.get("/chat/history")
def chat_history(
    limit: int = Query(default=20, ge=1, le=100),
    before_id: Optional[int] = Query(default=None, ge=1),
    video_id: Optional[int] = Query(default=None, ge=1),
    workspace: Dict = Depends(current_workspace),
):
    scoped_video_id = _verified_video_id(workspace["id"], video_id)
    return paged_chat_history(workspace["id"], limit=limit, before_id=before_id, video_id=scoped_video_id)


@router.post("/chat")
def chat(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    video_id = _verified_video_id(workspace["id"], payload.video_id)
    evidence = find_evidence(workspace["id"], payload.query, payload.limit, video_id, payload.evidence_mode)
    history = recent_chat_history(workspace["id"], video_id=video_id)
    answer_text = answer(payload.query, evidence, history)
    record_chat_message(workspace["id"], "user", payload.query, video_id=video_id)
    record_chat_message(workspace["id"], "assistant", answer_text, evidence, video_id=video_id)
    return {"answer": answer_text, "evidence": evidence}


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    """POST SSE: browser receives our stable events, not raw CLOVA event shapes."""
    video_id = _verified_video_id(workspace["id"], payload.video_id)
    evidence = find_evidence(workspace["id"], payload.query, payload.limit, video_id, payload.evidence_mode)
    history = recent_chat_history(workspace["id"], video_id=video_id)

    def sse(event: str, data: Dict) -> str:
        return "event: " + event + "\ndata: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n\n"

    def event_stream():
        yield "retry: 3000\n\n"
        yield sse("evidence", {"evidence": evidence})
        latest = ""
        try:
            for text in stream_answer(payload.query, evidence, history):
                latest = text
                yield sse("token", {"text": text})
            record_chat_message(workspace["id"], "user", payload.query, video_id=video_id)
            record_chat_message(workspace["id"], "assistant", latest, evidence, video_id=video_id)
            yield sse("done", {"evidence": evidence})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
