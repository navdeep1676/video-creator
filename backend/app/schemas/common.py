from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: ErrorBody


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None


class ProjectOut(ORMModel):
    id: UUID
    title: str
    description: str | None
    status: str
    storage_bytes: int
    created_at: Any
    updated_at: Any
    # Optional enrichment for list/dashboard (0 when not computed)
    slide_count: int = 0
    ready_audio_count: int = 0
    video_job_count: int = 0
    last_render_status: str | None = None


class NarrationOut(ORMModel):
    id: UUID
    text: str
    voice: str
    speed: float
    audio_key: str | None
    audio_url: str | None = None
    tts_status: str
    tts_error: str | None
    audio_duration_ms: int | None


class SlideOut(ORMModel):
    id: UUID
    project_id: UUID
    order_index: int
    image_key: str
    image_url: str | None = None
    duration_ms: int
    effective_duration_ms: int
    transition: str
    animation: str
    narration: NarrationOut | None = None


class SlideUpdate(BaseModel):
    text: str | None = None
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.8, le=1.2)
    duration_ms: int | None = Field(default=None, ge=500, le=120_000)
    transition: str | None = None
    animation: str | None = None


class ReorderRequest(BaseModel):
    slide_ids: list[UUID]


class TTSGenerateRequest(BaseModel):
    slide_id: UUID
    force: bool = False


class TTSBatchRequest(BaseModel):
    project_id: UUID
    force: bool = False


class TTSCancelRequest(BaseModel):
    project_id: UUID


class TTSStatusOut(BaseModel):
    slide_id: UUID
    tts_status: str
    audio_url: str | None = None
    audio_duration_ms: int | None = None
    tts_error: str | None = None


class VoiceOut(BaseModel):
    id: str
    name: str
    language: str
    language_label: str = "English"
    gender: str
    accent: str = ""
    provider: str = "edge"  # deepgram | edge (catalog primary)
    providers: list[str] = Field(default_factory=list)
    runtime_provider: str = "edge"  # what will actually run now
    requires_deepgram_key: bool = False


class LanguageOut(BaseModel):
    code: str
    label: str


class TTSProviderOut(BaseModel):
    id: str
    label: str
    available: bool
    description: str = ""


class TTSProvidersStatusOut(BaseModel):
    deepgram_available: bool
    edge_available: bool = True
    providers: list[TTSProviderOut] = Field(default_factory=list)


class ApplyLanguageRequest(BaseModel):
    project_id: UUID
    language: str = Field(min_length=2, max_length=8)
    voice: str | None = None
    regenerate: bool = False


class VideoRenderRequest(BaseModel):
    project_id: UUID
    include_subtitles: bool = True
    background_music_asset_id: UUID | None = None
    background_music_volume: float = Field(default=0.15, ge=0.0, le=1.0)


class VideoJobOut(ORMModel):
    id: UUID
    project_id: UUID
    status: str
    progress: int
    stage: str | None
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: Any
    started_at: Any | None
    finished_at: Any | None


class MusicAssetOut(ORMModel):
    id: UUID
    project_id: UUID
    filename: str
    size_bytes: int
    created_at: Any


class ListResponse(BaseModel):
    items: list[Any]
    total: int
