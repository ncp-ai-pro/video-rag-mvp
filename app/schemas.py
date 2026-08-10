from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ChannelCreate(BaseModel):
    url: HttpUrl
    name: Optional[str] = Field(default=None, max_length=200)


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
