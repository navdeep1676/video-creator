"""One ACE-Step track per project. Does not change the Naratto project status."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import MusicAsset, Project, StoryJob
from app.db.session import SessionLocal
from app.services.ace_step import AceStepMusicProvider, generate_music_bytes, mark_music_failed
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def music_storage_key(project_id: uuid.UUID) -> str:
    return f"projects/{project_id}/music/background.wav"


def build_music_provider(settings: Settings, override: AceStepMusicProvider | None = None) -> AceStepMusicProvider:
    if override is not None:
        return override
    return AceStepMusicProvider(settings)


def latest_job(session: Session, project_id: uuid.UUID, stage: str) -> StoryJob | None:
    return session.scalar(
        select(StoryJob)
        .where(StoryJob.project_id == project_id, StoryJob.stage == stage)
        .order_by(StoryJob.created_at.desc())
        .limit(1)
    )


def execute_music_job(job_id: uuid.UUID, provider: AceStepMusicProvider | None = None) -> None:
    settings = get_settings()
    session = SessionLocal()
    try:
        job = session.get(StoryJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        project = session.get(Project, job.project_id)
        if project is None:
            mark_music_failed(job, RuntimeError("Project not found"))
            session.commit()
            return
        job.status = "running"
        job.attempts += 1
        session.commit()
        active = build_music_provider(settings, provider)
        audio = generate_music_bytes(active, dict(job.payload or {}), settings)
        if audio is None:
            payload = dict(job.payload or {})
            payload["skipped"] = True
            job.payload = payload
        else:
            _store_track(session, project, audio)
        job.status = "succeeded"
        job.error = None
        session.commit()
        logger.info("[MUSIC] %s completed", project.id)
    except Exception as exc:
        session.rollback()
        logger.exception("[MUSIC] %s failed", job_id)
        failed = session.get(StoryJob, job_id)
        if failed is not None:
            mark_music_failed(failed, exc)
            session.commit()
    finally:
        session.close()


def _store_track(session: Session, project: Project, audio: bytes) -> None:
    storage = get_storage()
    key = music_storage_key(project.id)
    previous = storage.size(key) if storage.exists(key) else 0
    storage.put_bytes(key, audio)
    project.storage_bytes = max(0, int(project.storage_bytes or 0) + len(audio) - previous)
    asset = session.scalar(
        select(MusicAsset).where(MusicAsset.project_id == project.id, MusicAsset.storage_key == key)
    )
    if asset is None:
        session.add(
            MusicAsset(
                project_id=project.id,
                storage_key=key,
                filename="background.wav",
                size_bytes=len(audio),
            )
        )
    else:
        asset.filename = "background.wav"
        asset.size_bytes = len(audio)
    session.add(project)
