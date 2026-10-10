from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    projects: Mapped[list[Project]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_created", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="projects")
    slides: Mapped[list[Slide]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Slide.order_index"
    )
    video_jobs: Mapped[list[VideoJob]] = relationship(back_populates="project", cascade="all, delete-orphan")
    music_assets: Mapped[list[MusicAsset]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Slide(Base):
    __tablename__ = "slides"
    __table_args__ = (
        UniqueConstraint("project_id", "order_index", name="uq_slide_project_order"),
        Index("ix_slides_project_order", "project_id", "order_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Cover / primary image (first of image_keys). Nullable until images are added.
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Ordered list of storage keys — one slide can show multiple images (slideshow).
    image_keys: Mapped[list] = mapped_column(JSONB, default=list)
    duration_ms: Mapped[int] = mapped_column(Integer, default=5000)
    transition: Mapped[str] = mapped_column(String(32), default="fade")
    animation: Mapped[str] = mapped_column(String(32), default="none")
    # Optional prompt for Wan2.2 TI2V 5B (animation=wan_i2v or wan_t2v)
    motion_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="slides")
    narration: Mapped[Narration | None] = relationship(
        back_populates="slide", uselist=False, cascade="all, delete-orphan"
    )

    def all_image_entries(self) -> list[dict]:
        """
        Normalized ordered image entries: [{key, duration_ms}, ...].
        Supports legacy plain string keys and {key, duration_ms} objects.
        duration_ms=None means equal share at render time.
        """
        raw = list(self.image_keys or [])
        entries: list[dict] = []
        for item in raw:
            if isinstance(item, str) and item:
                entries.append({"key": item, "duration_ms": None})
            elif isinstance(item, dict):
                key = item.get("key") or item.get("image_key")
                if not key:
                    continue
                dur = item.get("duration_ms")
                try:
                    dur_i = int(dur) if dur is not None else None
                except (TypeError, ValueError):
                    dur_i = None
                if dur_i is not None and dur_i < 100:
                    dur_i = 100
                entries.append({"key": str(key), "duration_ms": dur_i})
        if not entries and self.image_key:
            entries = [{"key": self.image_key, "duration_ms": None}]
        return entries

    def all_image_keys(self) -> list[str]:
        """Normalized ordered image keys (falls back to legacy image_key)."""
        return [e["key"] for e in self.all_image_entries()]

    def set_image_entries(self, entries: list[dict]) -> None:
        """Persist normalized entries and keep cover image in sync."""
        cleaned: list[dict] = []
        for e in entries:
            key = e.get("key") if isinstance(e, dict) else None
            if not key:
                continue
            dur = e.get("duration_ms")
            try:
                dur_i = int(dur) if dur is not None else None
            except (TypeError, ValueError):
                dur_i = None
            if dur_i is not None and dur_i < 100:
                dur_i = 100
            cleaned.append({"key": str(key), "duration_ms": dur_i})
        self.image_keys = cleaned
        self.image_key = cleaned[0]["key"] if cleaned else None

    def sync_cover_image(self) -> None:
        self.set_image_entries(self.all_image_entries())


class Narration(Base):
    __tablename__ = "narrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slide_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), unique=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(String(64), default="edge-en-ava")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    audio_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tts_status: Mapped[str] = mapped_column(String(32), default="missing")
    tts_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    slide: Mapped[Slide] = relationship(back_populates="narration")


class MusicAsset(Base):
    __tablename__ = "music_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="music_assets")


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="video_jobs")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    title: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoryCharacter(Base):
    __tablename__ = "story_characters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    age: Mapped[str | None] = mapped_column(String(32), nullable=True)
    appearance: Mapped[str] = mapped_column(Text, default="")
    clothing: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(Text, default="")
    seed: Mapped[int] = mapped_column(Integer, default=0)


class StoryLocation(Base):
    __tablename__ = "story_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    lighting: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[str] = mapped_column(Text, default="")


class StoryScene(Base):
    __tablename__ = "story_scenes"
    __table_args__ = (UniqueConstraint("project_id", "index", name="uq_story_scene_project_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    beat: Mapped[str] = mapped_column(String(32), default="")
    start_time: Mapped[float] = mapped_column(Float, default=0)
    end_time: Mapped[float] = mapped_column(Float, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0)
    narration: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[str] = mapped_column(Text, default="")
    character_ids: Mapped[list] = mapped_column(JSONB, default=list)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("story_locations.id", ondelete="SET NULL"), nullable=True
    )
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    video_prompt: Mapped[str] = mapped_column(Text, default="")
    camera_motion: Mapped[str] = mapped_column(String(32), default="")
    transition: Mapped[str] = mapped_column(String(32), default="")
    sfx: Mapped[list] = mapped_column(JSONB, default=list)
    generation_mode: Mapped[str] = mapped_column(String(16), default="image")
    status: Mapped[str] = mapped_column(String(16), default="pending")


class StoryJob(Base):
    __tablename__ = "story_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(32), default="story")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
