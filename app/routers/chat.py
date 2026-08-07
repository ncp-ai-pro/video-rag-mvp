import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..dependencies import current_workspace
from ..schemas import ChatRequest
from ..services import answer, find_evidence, paged_chat_history, record_chat_message, recent_chat_history, stream_answer


router = APIRouter()


@router.get("/chat/history")
def chat_history(
    limit: int = Query(default=20, ge=1, le=100),
    before_id: Optional[int] = Query(default=None, ge=1),
    workspace: Dict = Depends(current_workspace),
):
    return paged_chat_history(workspace["id"], limit=limit, before_id=before_id)


@router.post("/chat")
def chat(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    evidence = find_evidence(workspace["id"], payload.query, payload.limit, payload.video_id)
    history = recent_chat_history(workspace["id"])
    answer_text = answer(payload.query, evidence, history)
    record_chat_message(workspace["id"], "user", payload.query)
    record_chat_message(workspace["id"], "assistant", answer_text, evidence)
    return {"answer": answer_text, "evidence": evidence}


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    """POST SSE: browser receives our stable events, not raw CLOVA event shapes."""
    evidence = find_evidence(workspace["id"], payload.query, payload.limit, payload.video_id)
    history = recent_chat_history(workspace["id"])

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
            record_chat_message(workspace["id"], "user", payload.query)
            record_chat_message(workspace["id"], "assistant", latest, evidence)
            yield sse("done", {"evidence": evidence})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
