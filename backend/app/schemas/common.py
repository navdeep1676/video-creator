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


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    # Locked at create: uploads + export use this frame
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16|1:1|4:5)$")


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    # Only allowed when the project has no slides yet
    aspect_ratio: str | None = Field(default=None, pattern=r"^(16:9|9:16|1:1|4:5)$")


class ProjectOut(ORMModel):
    id: UUID
    title: str
    description: str | None
    status: str
    storage_bytes: int
    created_at: Any
    updated_at: Any
    aspect_ratio: str = "16:9"
    canvas_width: int = 1920
    canvas_height: int = 1080
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


class SlideImageOut(BaseModel):
    index: int
    image_key: str
    image_url: str | None = None
    # Per-image hold time (ms). null = equal share of slide duration at render.
    duration_ms: int | None = None


class SlideOut(ORMModel):
    id: UUID
    project_id: UUID
    order_index: int
    image_key: str | None = None
    image_url: str | None = None
    images: list[SlideImageOut] = Field(default_factory=list)
    image_count: int = 0
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


class CreateSlideRequest(BaseModel):
    """Create an empty slide shell; attach images afterward."""
    transition: str = "fade"
    animation: str = "none"


class SlideImageUpdate(BaseModel):
    """Update a single image on a slide (currently duration)."""
    duration_ms: int | None = Field(default=None, ge=100, le=120_000)


class SlideImagesDurationsUpdate(BaseModel):
    """Set durations for multiple images by index."""
    items: list[dict]  # [{index: int, duration_ms: int|null}, ...]


class ReorderImagesRequest(BaseModel):
    """New order as zero-based indices into the current images list."""
    image_indices: list[int]


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
    # youtube | shorts | auto — platform-safe caption margins
    caption_style: str = Field(default="auto", pattern=r"^(auto|youtube|shorts)$")
    # Optional; when omitted, project.settings.aspect_ratio is used
    aspect_ratio: str | None = Field(default=None, pattern=r"^(16:9|9:16|1:1|4:5)$")
    # full = 1080-class; draft = ~720p faster preview encode
    quality: str = Field(default="full", pattern=r"^(full|draft)$")
    background_music_asset_id: UUID | None = None
    background_music_volume: float = Field(default=0.15, ge=0.0, le=1.0)


class AspectRatioOut(BaseModel):
    id: str
    label: str
    description: str
    width: int
    height: int
    category: str


class CaptionStyleOut(BaseModel):
    id: str
    label: str
    description: str
    margin_v_ratio: float
    margin_h_ratio: float
    font_scale: float
    max_chars: int
    max_words: int
    best_for: list[str]


class ExportCheckIssue(BaseModel):
    slide_id: UUID | None = None
    order: int | None = None
    message: str


class ExportCheckItem(BaseModel):
    id: str
    ok: bool
    label: str
    severity: str = "error"  # error | warning | info
    count: int = 0
    issues: list[ExportCheckIssue] = Field(default_factory=list)


class ExportReadinessOut(BaseModel):
    ready: bool
    project_id: UUID
    slide_count: int
    summary: dict[str, int]
    checks: list[ExportCheckItem]
    recommended_caption_style: str = "auto"


class VideoJobOut(ORMModel):
    id: UUID
    project_id: UUID
    status: str
    progress: int
    stage: str | None
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration_ms: int | None
    aspect_ratio: str | None = None
    width: int | None = None
    height: int | None = None
    quality: str | None = None
    caption_style: str | None = None
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
