from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ChannelCreate(BaseModel):
    url: HttpUrl
    name: Optional[str] = Field(default=None, max_length=200)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    color: Optional[str] = Field(default=None, max_length=40)


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    color: Optional[str] = Field(default=None, max_length=40)


class FolderVideoCreate(BaseModel):
    url: HttpUrl
    analyze: bool = True
    title: Optional[str] = Field(default=None, max_length=500)


class FolderVideoAttach(BaseModel):
    analyze: bool = False
    source: str = Field(default="manual", max_length=40)


class ChannelSourceCreate(BaseModel):
    url: HttpUrl
    name: Optional[str] = Field(default=None, max_length=200)
    auto_scan: bool = True


class VideoCreate(BaseModel):
    platform_video_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    url: HttpUrl
    thumbnail_url: Optional[HttpUrl] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    uploaded_at: Optional[str] = None


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)


class TranscriptImport(BaseModel):
    segments: List[TranscriptSegment] = Field(min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class ChatRequest(SearchRequest):
    limit: int = Field(default=3, ge=1, le=3)
    video_id: Optional[int] = None
    evidence_mode: Literal["simple", "precise", "ultra"] = "simple"


class WorkspaceConnect(BaseModel):
    workspace_code: str = Field(min_length=6, max_length=16)

# https://api.ncloud-docs.com/docs/ai-naver-clovavoice-ttspremium
class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    speaker: str = Field(default="nyounghwa", max_length=50)
