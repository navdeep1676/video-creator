"""One project snapshot for the SSE stream.

The browser opens a single stream. The server reads the database about once a
second and sends a message only when a job, slide, or render actually changed.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import MusicAsset, Project, Slide, Story, StoryScene, VideoJob
from app.db.session import SessionLocal
from app.services.music_job import latest_job, music_storage_key
from app.services.media_tokens import signed_url_path
from app.services.stage_job import job_view
from app.services.story_job import latest_story_job

_SYNC_KEYS = ("job", "music", "images", "slides", "videos")


def sync_delta(previous: dict | None, current: dict) -> dict | None:
    """Fields that changed since the last push. The first push sends the data, not a story reload."""
    if previous == current:
        return None
    delta: dict[str, Any] = {}
    for key in _SYNC_KEYS:
        if previous is None or previous.get(key) != current.get(key):
            delta[key] = current.get(key)
    if previous is not None and previous.get("story_version") != current.get("story_version"):
        delta["reload_story"] = True
    return delta or None


def encode_sync_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def read_project_sync(project_id: UUID, user_id: UUID) -> dict | None:
    """Current jobs, slides, and recent renders. None when the project is not this user's."""
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None or project.owner_id != user_id:
            return None
        return _snapshot(db, project, user_id)
    finally:
        db.close()


def _snapshot(db: Session, project: Project, user_id: UUID) -> dict:
    from app.api.slides import _slide_out
    from app.api.video import _job_out as video_job_out

    story_job = latest_story_job(db, project.id)
    music_job = latest_job(db, project.id, "music")
    image_job = latest_job(db, project.id, "images")
    music_key = music_storage_key(project.id)
    music_asset = db.scalar(
        select(MusicAsset).where(MusicAsset.project_id == project.id, MusicAsset.storage_key == music_key)
    )
    story = db.scalar(select(Story).where(Story.project_id == project.id))
    scene_count = db.scalar(
        select(func.count()).select_from(StoryScene).where(StoryScene.project_id == project.id)
    )
    slides = db.scalars(
        select(Slide)
        .options(selectinload(Slide.narration))
        .where(Slide.project_id == project.id)
        .order_by(Slide.order_index)
    ).all()
    videos = db.scalars(
        select(VideoJob).where(VideoJob.project_id == project.id).order_by(VideoJob.created_at.desc()).limit(3)
    ).all()
    return {
        "job": None if story_job is None else job_view(story_job),
        "music": {
            "job": None if music_job is None else job_view(music_job),
            "audio_url": signed_url_path(music_key, str(user_id)) if music_asset is not None else None,
            "filename": None if music_asset is None else music_asset.filename,
        },
        "images": {"job": None if image_job is None else job_view(image_job)},
        "slides": [_slide_out(slide, user_id).model_dump(mode="json") for slide in slides],
        "videos": [video_job_out(job, user_id).model_dump(mode="json") for job in videos],
        "story_version": f"{getattr(story, 'id', '')}:{len(story.body) if story is not None else 0}:{scene_count or 0}",
    }
