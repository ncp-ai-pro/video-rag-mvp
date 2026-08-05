import json
from typing import Dict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..dependencies import current_workspace
from ..schemas import ChatRequest
from ..services import answer, find_evidence, stream_answer


router = APIRouter()


@router.post("/chat")
def chat(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    evidence = find_evidence(workspace["id"], payload.query, payload.limit)
    return {"answer": answer(payload.query, evidence), "evidence": evidence}


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    """POST SSE: browser receives our stable events, not raw CLOVA event shapes."""
    evidence = find_evidence(workspace["id"], payload.query, payload.limit)

    def sse(event: str, data: Dict) -> str:
        return "event: " + event + "\ndata: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n\n"

    def event_stream():
        yield "retry: 3000\n\n"
        yield sse("evidence", {"evidence": evidence})
        try:
            for text in stream_answer(payload.query, evidence):
                yield sse("token", {"text": text})
            yield sse("done", {"evidence": evidence})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
