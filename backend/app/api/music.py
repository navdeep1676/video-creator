from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.projects import get_owned_project
from app.config import get_settings
from app.db.models import MusicAsset, Slide, Story, StoryJob, StoryScene, User
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import MusicAssetOut
from app.services.duration import effective_duration_ms
from app.services.stage_job import dispatch_stage_task, job_view
from app.services.story_slides import align_story_slide_durations
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


def _scene_cues(db: Session, project_id: UUID, plan: dict) -> list[dict]:
    """One cue per scene. Durations follow the same timeline the video will use."""
    align_story_slide_durations(db, project_id)
    rows = list(
        db.scalars(select(StoryScene).where(StoryScene.project_id == project_id).order_by(StoryScene.index)).all()
    )
    slides = list(
        db.scalars(
            select(Slide)
            .options(selectinload(Slide.narration))
            .where(Slide.project_id == project_id)
            .order_by(Slide.order_index)
        ).all()
    )
    slide_by_index = {slide.order_index: slide for slide in slides}
    planned = plan.get("scenes") if isinstance(plan.get("scenes"), list) else []
    cues = []
    cursor = 0.0
    for row in rows:
        draft = planned[row.index] if row.index < len(planned) and isinstance(planned[row.index], dict) else {}
        slide = slide_by_index.get(row.index)
        seconds = float(row.duration or 0)
        if slide is not None:
            seconds = effective_duration_ms(slide, slide.narration) / 1000.0
        start = round(cursor, 3)
        cursor += seconds
        cues.append(
            {
                "index": row.index,
                "beat": row.beat,
                "duration": round(seconds, 3),
                "start_time": start,
                "end_time": round(cursor, 3),
                "narration": row.narration or "",
                "location": str(draft.get("location_name") or ""),
                "music_prompt": str(draft.get("music_prompt") or ""),
            }
        )
    return cues


def _music_job_out(job: StoryJob) -> dict:
    return job_view(job)


@router.post("/projects/{project_id}/music/generate", response_model=None)
def generate_music(
    project_id: UUID,
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
    content_type = saved.get("content_type") or "horror"
    payload = {
        "content_type": content_type,
        "music_mode": music_mode,
        "music_prompt": plan.get("music_prompt") or "",
        "lyrics": story.lyrics or "",
        "duration_seconds": saved.get("duration_seconds") or 30,
        "language": saved.get("language") or "en",
        "scenes": _scene_cues(db, project.id, plan),
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
    from app.workers.tasks import generate_music as generate_music_task

    dispatch_stage_task(db, job, lambda: generate_music_task.delay(str(job.id)))
    return JSONResponse(_music_job_out(job), status_code=202)
