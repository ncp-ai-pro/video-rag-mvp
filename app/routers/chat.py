from typing import Dict

from fastapi import APIRouter, Depends

from ..dependencies import current_workspace
from ..schemas import ChatRequest
from ..services import answer, find_evidence


router = APIRouter()


@router.post("/chat")
def chat(payload: ChatRequest, workspace: Dict = Depends(current_workspace)):
    evidence = find_evidence(workspace["id"], payload.query, payload.limit)
    return {"answer": answer(payload.query, evidence), "evidence": evidence}
