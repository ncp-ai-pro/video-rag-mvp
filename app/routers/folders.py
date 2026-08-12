import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..dependencies import current_workspace
from ..db import is_unique_violation
from ..folders import (
    add_video_url_to_folder,
    analyze_candidate,
    attach_existing_video_to_folder,
    channel_source_belongs_to_folder,
    create_channel_source,
    create_folder,
    delete_folder,
    list_channel_sources,
    list_folder_candidates,
    list_folder_videos,
    list_folders,
    remove_folder_video,
    required_folder,
    update_folder,
    video_belongs_to_folder,
)
from ..schemas import (
    ChannelSourceCreate,
    ChatRequest,
    FolderCreate,
    FolderUpdate,
    FolderVideoAttach,
    FolderVideoCreate,
    SearchRequest,
)
from ..services import (
    answer,
    enqueue,
    find_evidence,
    find_metadata,
    paged_chat_history,
    record_chat_message,
    recent_chat_history,
    stream_answer,
)


router = APIRouter(prefix="/folders", tags=["folders"])


def _not_found(exc: LookupError):
    raise HTTPException(status_code=404, detail=str(exc))


@router.get("")
def folders(workspace: Dict = Depends(current_workspace)):
    return list_folders(workspace["id"])


@router.post("", status_code=status.HTTP_201_CREATED)
def folder_create(payload: FolderCreate, workspace: Dict = Depends(current_workspace)):
    try:
        return create_folder(workspace["id"], payload.model_dump())
    except Exception as exc:
        if is_unique_violation(exc):
            raise HTTPException(status_code=409, detail="folder already exists in this workspace")
        raise


@router.get("/{folder_id}")
def folder_detail(folder_id: int, workspace: Dict = Depends(current_workspace)):
    try:
        folder = required_folder(folder_id, workspace["id"])
    except LookupError as exc:
        _not_found(exc)
    folder["videos"] = list_folder_videos(workspace["id"], folder_id, limit=10)
    folder["channel_sources"] = list_channel_sources(workspace["id"], folder_id)
    return folder


@router.patch("/{folder_id}")
def folder_update(folder_id: int, payload: FolderUpdate, workspace: Dict = Depends(current_workspace)):
    try:
        return update_folder(workspace["id"], folder_id, payload.model_dump(exclude_unset=True))
    except LookupError as exc:
        _not_found(exc)
    except Exception as exc:
        if is_unique_violation(exc):
            raise HTTPException(status_code=409, detail="folder already exists in this workspace")
        raise


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def folder_delete(folder_id: int, workspace: Dict = Depends(current_workspace)):
    try:
        delete_folder(workspace["id"], folder_id)
    except LookupError as exc:
        _not_found(exc)


@router.get("/{folder_id}/videos")
def folder_videos(
    folder_id: int,
    status_filter: str = Query(default="all", alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    workspace: Dict = Depends(current_workspace),
):
    try:
        return list_folder_videos(workspace["id"], folder_id, status_filter=status_filter, query=q, limit=limit)
    except LookupError as exc:
        _not_found(exc)


@router.post("/{folder_id}/videos", status_code=status.HTTP_201_CREATED)
def folder_video_create(folder_id: int, payload: FolderVideoCreate, workspace: Dict = Depends(current_workspace)):
    try:
        return add_video_url_to_folder(
            workspace["id"],
            folder_id,
            str(payload.url),
            analyze=payload.analyze,
            title=payload.title,
        )
    except LookupError as exc:
        _not_found(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{folder_id}/videos/{video_id}", status_code=status.HTTP_201_CREATED)
def folder_video_attach(
    folder_id: int,
    video_id: int,
    payload: FolderVideoAttach,
    workspace: Dict = Depends(current_workspace),
):
    try:
        return attach_existing_video_to_folder(
            workspace["id"],
            folder_id,
            video_id,
            source=payload.source,
            analyze=payload.analyze,
        )
    except LookupError as exc:
        _not_found(exc)


@router.delete("/{folder_id}/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def folder_video_delete(folder_id: int, video_id: int, workspace: Dict = Depends(current_workspace)):
    try:
        remove_folder_video(workspace["id"], folder_id, video_id)
    except LookupError as exc:
        _not_found(exc)


@router.get("/{folder_id}/channel-sources")
def folder_channel_sources(folder_id: int, workspace: Dict = Depends(current_workspace)):
    try:
        return list_channel_sources(workspace["id"], folder_id)
    except LookupError as exc:
        _not_found(exc)


@router.post("/{folder_id}/channel-sources", status_code=status.HTTP_201_CREATED)
def folder_channel_source_create(
    folder_id: int,
    payload: ChannelSourceCreate,
    workspace: Dict = Depends(current_workspace),
):
    try:
        source = create_channel_source(workspace["id"], folder_id, str(payload.url), payload.name)
    except LookupError as exc:
        _not_found(exc)
    scan_job = {"job_id": enqueue("scan_channel", source["id"]), "status": "queued"} if payload.auto_scan else None
    return {**source, "scan_job": scan_job}


@router.post("/{folder_id}/channel-sources/{source_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def folder_channel_source_scan(folder_id: int, source_id: int, workspace: Dict = Depends(current_workspace)):
    if not channel_source_belongs_to_folder(workspace["id"], folder_id, source_id):
        raise HTTPException(status_code=404, detail="channel source not found")
    return {"job_id": enqueue("scan_channel", source_id), "status": "queued"}


@router.get("/{folder_id}/candidates")
def folder_candidates(
    folder_id: int,
    status_filter: str = Query(default="new", alias="status"),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    workspace: Dict = Depends(current_workspace),
):
    try:
        return list_folder_candidates(workspace["id"], folder_id, status_filter=status_filter, query=q, limit=limit)
    except LookupError as exc:
        _not_found(exc)


@router.post("/{folder_id}/candidates/{candidate_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def folder_candidate_analyze(folder_id: int, candidate_id: int, workspace: Dict = Depends(current_workspace)):
    try:
        return analyze_candidate(workspace["id"], folder_id, candidate_id, analyze=True)
    except LookupError as exc:
        _not_found(exc)


@router.post("/{folder_id}/recommendations")
def folder_recommendations(folder_id: int, payload: SearchRequest, workspace: Dict = Depends(current_workspace)):
    try:
        required_folder(folder_id, workspace["id"])
    except LookupError as exc:
        _not_found(exc)
    return {
        "query": payload.query,
        "items": find_metadata(workspace["id"], payload.query, payload.limit),
        "notice": "추천은 제목과 영상 설명의 embedding 유사도 기반이며 영상 내용을 검증하지 않습니다.",
    }


@router.get("/{folder_id}/chat/history")
def folder_chat_history(
    folder_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    before_id: Optional[int] = Query(default=None, ge=1),
    video_id: Optional[int] = Query(default=None, ge=1),
    workspace: Dict = Depends(current_workspace),
):
    try:
        required_folder(folder_id, workspace["id"])
    except LookupError as exc:
        _not_found(exc)
    if video_id is not None and not video_belongs_to_folder(workspace["id"], folder_id, video_id):
        raise HTTPException(status_code=404, detail="video not found in folder")
    return paged_chat_history(
        workspace["id"],
        limit=limit,
        before_id=before_id,
        video_id=video_id,
        folder_id=folder_id,
    )


@router.post("/{folder_id}/chat")
def folder_chat(folder_id: int, payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    try:
        required_folder(folder_id, workspace["id"])
    except LookupError as exc:
        _not_found(exc)
    if payload.video_id is not None and not video_belongs_to_folder(workspace["id"], folder_id, payload.video_id):
        raise HTTPException(status_code=404, detail="video not found in folder")
    evidence = find_evidence(
        workspace["id"],
        payload.query,
        payload.limit,
        payload.video_id,
        payload.evidence_mode,
        folder_id,
    )
    history = recent_chat_history(workspace["id"], video_id=payload.video_id, folder_id=folder_id)
    answer_text = answer(payload.query, evidence, history)
    record_chat_message(workspace["id"], "user", payload.query, video_id=payload.video_id, folder_id=folder_id)
    record_chat_message(
        workspace["id"], "assistant", answer_text, evidence, video_id=payload.video_id, folder_id=folder_id
    )
    return {"answer": answer_text, "evidence": evidence}


@router.post("/{folder_id}/chat/stream")
def folder_chat_stream(folder_id: int, payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    try:
        required_folder(folder_id, workspace["id"])
    except LookupError as exc:
        _not_found(exc)
    if payload.video_id is not None and not video_belongs_to_folder(workspace["id"], folder_id, payload.video_id):
        raise HTTPException(status_code=404, detail="video not found in folder")
    evidence = find_evidence(
        workspace["id"],
        payload.query,
        payload.limit,
        payload.video_id,
        payload.evidence_mode,
        folder_id,
    )
    history = recent_chat_history(workspace["id"], video_id=payload.video_id, folder_id=folder_id)

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
            record_chat_message(workspace["id"], "user", payload.query, video_id=payload.video_id, folder_id=folder_id)
            record_chat_message(
                workspace["id"], "assistant", latest, evidence, video_id=payload.video_id, folder_id=folder_id
            )
            yield sse("done", {"evidence": evidence})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
