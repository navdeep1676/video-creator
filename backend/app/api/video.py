from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.projects import get_owned_project
from app.config import get_settings
from app.db.models import MusicAsset, Project, Slide, User, VideoJob
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import ListResponse, VideoJobOut, VideoRenderRequest
from app.services.duration import effective_duration_ms
from app.services.media_tokens import signed_url_path
from app.services.storage import LocalStorage
from app.services.job_control import cancel_project_jobs, cancel_video_job
from app.utils.exceptions import AppError
from app.workers.tasks import render_video

router = APIRouter(prefix="/video", tags=["video"])


def _job_out(job: VideoJob, user_id: UUID) -> VideoJobOut:
    return VideoJobOut(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        video_url=signed_url_path(job.video_key, str(user_id)) if job.video_key else None,
        thumbnail_url=signed_url_path(job.thumbnail_key, str(user_id)) if job.thumbnail_key else None,
        duration_ms=job.duration_ms,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("/render", response_model=VideoJobOut)
def start_render(
    body: VideoRenderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoJobOut:
    settings = get_settings()
    # Lock project row to serialize concurrent render requests
    project = db.execute(select(Project).where(Project.id == body.project_id).with_for_update()).scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise AppError("NOT_FOUND", "Project not found", 404)

    active = db.scalar(
        select(VideoJob).where(
            VideoJob.project_id == project.id,
            VideoJob.status.in_(["queued", "processing"]),
        )
    )
    if active:
        raise AppError("RENDER_IN_PROGRESS", "A render job is already active for this project", 409)

    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.project_id == project.id).order_by(Slide.order_index)
    ).all()
    if not slides:
        raise AppError("VALIDATION", "Project has no slides", 400)

    # TTS must not be in progress
    for s in slides:
        n = s.narration
        if n and n.tts_status in {"queued", "processing"}:
            raise AppError("TTS_IN_PROGRESS", "Wait for TTS jobs to finish before rendering", 409)
        if not n or not (n.text or "").strip():
            raise AppError("VALIDATION", f"Slide {s.order_index + 1} is missing narration text", 400)
        if n.tts_status != "ready" or not n.audio_key:
            raise AppError("VALIDATION", f"Slide {s.order_index + 1} needs TTS audio before render", 400)

    total_ms = sum(effective_duration_ms(s, s.narration) for s in slides)
    if total_ms / 1000 > settings.max_video_duration_s:
        raise AppError("DURATION_CAP", "Total video duration exceeds 20 minutes", 400)

    if body.background_music_asset_id:
        if not settings.feature_bgm:
            raise AppError("FEATURE_DISABLED", "Background music is disabled", 400)
        music = db.get(MusicAsset, body.background_music_asset_id)
        if not music or music.project_id != project.id:
            raise AppError("NOT_FOUND", "Music asset not found", 404)

    job = VideoJob(
        project_id=project.id,
        user_id=user.id,
        status="queued",
        progress=0,
        stage="queued",
        options={
            "include_subtitles": body.include_subtitles,
            "background_music_asset_id": str(body.background_music_asset_id)
            if body.background_music_asset_id
            else None,
            "background_music_volume": body.background_music_volume,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    async_result = render_video.delay(str(job.id))
    job.celery_task_id = async_result.id
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_out(job, user.id)


@router.get("/status/{job_id}", response_model=VideoJobOut)
def job_status(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoJobOut:
    job = db.get(VideoJob, job_id)
    if not job:
        raise AppError("NOT_FOUND", "Job not found", 404)
    get_owned_project(db, job.project_id, user)
    return _job_out(job, user.id)


@router.post("/jobs/{job_id}/cancel", response_model=VideoJobOut)
def cancel_render(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoJobOut:
    """Stop a queued or processing video render job."""
    job = db.get(VideoJob, job_id)
    if not job:
        raise AppError("NOT_FOUND", "Job not found", 404)
    get_owned_project(db, job.project_id, user)
    if job.status not in {"queued", "processing"}:
        raise AppError("NOT_ACTIVE", f"Job is already {job.status}", 400)
    job = cancel_video_job(db, job)
    return _job_out(job, user.id)


@router.post("/projects/{project_id}/stop")
def stop_project_jobs(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Stop all active TTS and render jobs for a project."""
    project = get_owned_project(db, project_id, user)
    result = cancel_project_jobs(db, project)
    return {"ok": True, **result}


@router.get("/download/{job_id}")
def download_video(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> FileResponse:
    job = db.get(VideoJob, job_id)
    if not job:
        raise AppError("NOT_FOUND", "Job not found", 404)
    get_owned_project(db, job.project_id, user)
    if job.status != "completed" or not job.video_key:
        raise AppError("NOT_READY", "Video is not ready", 400)
    path = storage.absolute_path(job.video_key)
    if not path.is_file():
        raise AppError("NOT_FOUND", "Video file missing", 404)
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")


@router.get("/projects/{project_id}/videos", response_model=ListResponse)
def list_videos(
    project_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListResponse:
    get_owned_project(db, project_id, user)
    q = select(VideoJob).where(VideoJob.project_id == project_id).order_by(VideoJob.created_at.desc())
    items = db.scalars(q.limit(limit).offset(offset)).all()
    total = len(db.scalars(select(VideoJob).where(VideoJob.project_id == project_id)).all())
    return ListResponse(items=[_job_out(j, user.id) for j in items], total=total)
