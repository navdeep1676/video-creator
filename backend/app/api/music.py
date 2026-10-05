from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.projects import get_owned_project
from app.config import get_settings
from app.db.models import MusicAsset, Story, StoryJob, User
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import MusicAssetOut
from app.services.music_job import execute_music_job
from app.services.storage import LocalStorage
from app.services.story_job import latest_story_job
from app.utils.exceptions import AppError
from app.utils.files import validate_audio_bytes

router = APIRouter(tags=["music"])


@router.get("/projects/{project_id}/music", response_model=list[MusicAssetOut])
def list_music(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MusicAsset]:
    project = get_owned_project(db, project_id, user)
    return list(db.scalars(select(MusicAsset).where(MusicAsset.project_id == project.id)).all())


@router.post("/projects/{project_id}/music", response_model=MusicAssetOut)
async def upload_music(
    project_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> MusicAsset:
    settings = get_settings()
    if not settings.feature_bgm:
        raise AppError("FEATURE_DISABLED", "Background music is disabled", 400)
    project = get_owned_project(db, project_id, user)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", "Music file exceeds 20MB", 413)
    try:
        ext = validate_audio_bytes(data, file.filename or "track.mp3")
    except ValueError as e:
        raise AppError("INVALID_AUDIO", str(e), 400) from e
    asset_id = uuid4()
    key = f"uploads/{project.id}/music/{asset_id}{ext}"
    storage.put_bytes(key, data)
    project.storage_bytes += len(data)
    asset = MusicAsset(
        id=asset_id,
        project_id=project.id,
        storage_key=key,
        filename=file.filename or f"{asset_id}{ext}",
        size_bytes=len(data),
    )
    db.add(asset)
    db.add(project)
    db.commit()
    db.refresh(asset)
    return asset


class MusicGenerateRequest(BaseModel):
    music_mode: Literal["none", "background", "full_song"] | None = None


def _music_job_out(job: StoryJob) -> dict:
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "stage": job.stage,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
    }


@router.post("/projects/{project_id}/music/generate", response_model=None)
def generate_music(
    project_id: UUID,
    request: Request,
    background: BackgroundTasks,
    body: MusicGenerateRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse | dict:
    settings = get_settings()
    if not settings.feature_bgm:
        raise AppError("FEATURE_DISABLED", "Background music is disabled", 400)
    project = get_owned_project(db, project_id, user)
    story = db.scalar(select(Story).where(Story.project_id == project.id))
    if story is None:
        raise AppError("VALIDATION", "Generate a story before music", 400)
    story_job = latest_story_job(db, project.id)
    if story_job is not None and story_job.status in {"queued", "running"}:
        raise AppError("BUSY", "Wait until the story finishes before generating music", 409)
    saved = dict((project.settings or {}).get("story") or {})
    music_mode = (body.music_mode if body is not None else None) or saved.get("music_mode") or "background"
    if music_mode == "none":
        return {"status": "skipped", "job": None}
    active = db.scalar(
        select(StoryJob).where(
            StoryJob.project_id == project.id,
            StoryJob.stage == "music",
            StoryJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        return JSONResponse(_music_job_out(active), status_code=202)
    plan = story.plan if isinstance(story.plan, dict) else {}
    payload = {
        "content_type": saved.get("content_type") or "horror",
        "music_mode": music_mode,
        "music_prompt": plan.get("music_prompt") or "",
        "lyrics": story.lyrics or "",
        "duration_seconds": saved.get("duration_seconds") or 30,
        "language": saved.get("language") or "en",
    }
    saved["music_mode"] = music_mode
    stored = dict(project.settings or {})
    stored["story"] = saved
    project.settings = stored
    job = StoryJob(project_id=project.id, stage="music", status="queued", attempts=0, payload=payload)
    db.add(job)
    db.add(project)
    db.commit()
    db.refresh(job)
    background.add_task(execute_music_job, job.id, getattr(request.app.state, "music_provider", None))
    return JSONResponse(_music_job_out(job), status_code=202)
