import httpx
import re
import time #병렬구조 시간측정
import asyncio #병렬

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..config import CLOVA_VOICE_CLIENT_ID, CLOVA_VOICE_CLIENT_SECRET, CLOVA_VOICE_URL
from ..schemas import TTSRequest

router = APIRouter()

def split_text(text: str, max_len: int = 400) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) > max_len:
            if cur: chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur: chunks.append(cur)
    return [c for c in chunks if re.search(r"[가-힣a-zA-Z]", c)]

def clean_for_tts(text: str) -> str:
    """Strips markdown and list numbering that CLOVA renders as noise or long pauses."""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"[#`_~>|]", "", text)
    text = re.sub(r"(?<=[.!?])(?=[^\s])", " ", text)
    text = re.sub(r"(?m)^\s*(\d+)\.\s+", r"\1번, ", text)
    return re.sub(r"\s+", " ", text).strip()


@router.post("/tts")
async def create_speech(payload: TTSRequest):
    if not CLOVA_VOICE_CLIENT_ID or not CLOVA_VOICE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="CLOVA Voice가 설정되어 있지 않습니다.")

    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLOVA_VOICE_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": CLOVA_VOICE_CLIENT_SECRET,
    }
    chunks = split_text(clean_for_tts(payload.text))
    print(f"[TTS] {len(chunks)} chunks: {[len(c) for c in chunks]}")
    audio = bytearray()

    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=60.0) as client:
        async def fetch(chunk: str) -> bytes:
            response = await client.post(
                CLOVA_VOICE_URL,
                headers=headers,
                data={
                    "speaker": payload.speaker,
                    "text": chunk,
                    "format": "mp3",
                    "speed": "0",
                },
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"CLOVA Voice error: {response.text}",
                )
            return response.content

        parts = await asyncio.gather(*(fetch(c) for c in chunks))

    end = time.perf_counter()
    print(f"[TTS] parallel: {end - start:.2f}s")

    return Response(content=b"".join(parts), media_type="audio/mpeg")