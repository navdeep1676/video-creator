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
from app.schemas.common import (
    AspectRatioOut,
    CaptionStyleOut,
    ExportReadinessOut,
    ListResponse,
    VideoJobOut,
    VideoRenderRequest,
)
from app.services.aspect_ratios import (
    ASPECT_RATIO_PRESETS,
    canvas_for_quality,
    project_aspect_ratio,
    resolve_aspect_ratio,
)
from app.services.caption_styles import (
    CAPTION_STYLE_PACKS,
    DEFAULT_CAPTION_STYLE,
    caption_style_public_dict,
    resolve_caption_style,
)
from app.services.duration import effective_duration_ms
from app.services.export_readiness import build_export_readiness, slides_for_render
from app.services.media_tokens import signed_url_path
from app.services.storage import LocalStorage
from app.services.job_control import cancel_project_jobs, cancel_video_job
from app.utils.exceptions import AppError
from app.workers.tasks import render_video

router = APIRouter(prefix="/video", tags=["video"])


def _job_out(job: VideoJob, user_id: UUID) -> VideoJobOut:
    opts = job.options or {}
    ar = opts.get("aspect_ratio")
    width = opts.get("width")
    height = opts.get("height")
    quality = opts.get("quality") or "full"
    caption_style = opts.get("caption_style")
    raw_slide = opts.get("slide_id")
    slide_id = None
    if raw_slide:
        try:
            slide_id = UUID(str(raw_slide))
        except ValueError:
            slide_id = None
    raw_order = opts.get("slide_order")
    slide_order = int(raw_order) if raw_order else None
    if ar and (not width or not height):
        try:
            preset = resolve_aspect_ratio(str(ar))
            w, h, _, _ = canvas_for_quality(preset, str(quality))
            width = width or w
            height = height or h
        except ValueError:
            pass
    return VideoJobOut(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        video_url=signed_url_path(job.video_key, str(user_id)) if job.video_key else None,
        thumbnail_url=signed_url_path(job.thumbnail_key, str(user_id)) if job.thumbnail_key else None,
        duration_ms=job.duration_ms,
        aspect_ratio=str(ar) if ar else None,
        width=int(width) if width else None,
        height=int(height) if height else None,
        quality=str(quality) if quality else None,
        caption_style=str(caption_style) if caption_style else None,
        slide_id=slide_id,
        slide_order=slide_order,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/aspect-ratios", response_model=ListResponse)
def list_aspect_ratios(
    user: User = Depends(get_current_user),
) -> ListResponse:
    """Available export aspect ratios (long-form, shorts, square, social)."""
    items = [
        AspectRatioOut(
            id=p.id,
            label=p.label,
            description=p.description,
            width=p.width,
            height=p.height,
            category=p.category,
        )
        for p in ASPECT_RATIO_PRESETS.values()
    ]
    return ListResponse(items=items, total=len(items))


@router.get("/wan-i2v/status")
def wan_i2v_capability(
    user: User = Depends(get_current_user),
) -> dict:
    """Wan2.1 image-to-video backend status (mock vs GPU Diffusers/CLI)."""
    from app.services.wan_i2v import wan_i2v_status

    return wan_i2v_status()


@router.get("/wan-t2v/status")
def wan_t2v_capability(
    user: User = Depends(get_current_user),
) -> dict:
    """Wan2.2 TI2V 5B status. Local Diffusers or official CLI, not ComfyUI."""
    from app.services.wan_t2v import wan_t2v_status

    return wan_t2v_status()


@router.get("/caption-styles", response_model=ListResponse)
def list_caption_styles(
    user: User = Depends(get_current_user),
) -> ListResponse:
    """Caption style packs with platform-safe margins (YouTube vs Shorts)."""
    items = [
        CaptionStyleOut(**caption_style_public_dict(p))
        for p in CAPTION_STYLE_PACKS.values()
    ]
    return ListResponse(items=items, total=len(items))


@router.get("/projects/{project_id}/export-readiness", response_model=ExportReadinessOut)
def export_readiness(
    project_id: UUID,
    slide_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExportReadinessOut:
    """Pre-render checklist: missing images, empty narration, missing/in-progress TTS.

    Pass slide_id to check only that slide before a single-slide video.
    """
    project = get_owned_project(db, project_id, user)
    slides = list(
        db.scalars(
            select(Slide)
            .options(selectinload(Slide.narration))
            .where(Slide.project_id == project.id)
            .order_by(Slide.order_index)
        ).all()
    )
    single = slide_id is not None
    if single:
        slides = slides_for_render(slides, slide_id)
        if not slides:
            raise AppError("NOT_FOUND", "Slide not found", 404)
    return build_export_readiness(project, slides, single_slide=single)


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

    slides = list(
        db.scalars(
            select(Slide)
            .options(selectinload(Slide.narration))
            .where(Slide.project_id == project.id)
            .order_by(Slide.order_index)
        ).all()
    )
    single = body.slide_id is not None
    if single:
        slides = slides_for_render(slides, body.slide_id)
        if not slides:
            raise AppError("NOT_FOUND", "Slide not found", 404)
    elif not slides:
        raise AppError("VALIDATION", "Project has no slides", 400)

    readiness = build_export_readiness(project, slides, single_slide=single)
    if not readiness.ready:
        details = {
            "summary": readiness.summary,
            "checks": [c.model_dump(mode="json") for c in readiness.checks if not c.ok],
        }
        # Prefer a clear first error message
        first_issue = next(
            (iss.message for c in readiness.checks if not c.ok for iss in c.issues),
            "Project is not ready to export",
        )
        code = "TTS_IN_PROGRESS" if readiness.summary.get("tts_in_progress") else "EXPORT_NOT_READY"
        status = 409 if code == "TTS_IN_PROGRESS" else 400
        raise AppError(code, first_issue, status, details=details)

    total_ms = sum(effective_duration_ms(s, s.narration) for s in slides)
    if total_ms / 1000 > settings.max_video_duration_s:
        raise AppError("DURATION_CAP", "Total video duration exceeds 20 minutes", 400)

    if body.background_music_asset_id:
        if not settings.feature_bgm:
            raise AppError("FEATURE_DISABLED", "Background music is disabled", 400)
        music = db.get(MusicAsset, body.background_music_asset_id)
        if not music or music.project_id != project.id:
            raise AppError("NOT_FOUND", "Music asset not found", 404)

    # Project format is the source of truth (chosen at create; uploads already validated)
    project_preset = project_aspect_ratio(project.settings)
    if body.aspect_ratio and body.aspect_ratio != project_preset.id:
        raise AppError(
            "ASPECT_LOCKED",
            f"This project is {project_preset.id} ({project_preset.label}). "
            "Create a new project to export a different ratio.",
            400,
        )
    preset = project_preset
    quality = (body.quality or "full").strip().lower()
    if quality not in {"full", "draft"}:
        raise AppError("VALIDATION", "quality must be full or draft", 400)
    caption_style = (body.caption_style or DEFAULT_CAPTION_STYLE).strip().lower()
    if caption_style not in CAPTION_STYLE_PACKS:
        raise AppError("VALIDATION", "caption_style must be auto, youtube, or shorts", 400)
    render_w, render_h, crf, fps = canvas_for_quality(preset, quality)
    x264_preset = "veryfast" if quality == "draft" else "medium"
    resolved_pack = resolve_caption_style(
        caption_style, width=render_w, height=render_h, aspect_ratio=preset.id
    )

    job = VideoJob(
        project_id=project.id,
        user_id=user.id,
        status="queued",
        progress=0,
        stage="queued",
        options={
            "include_subtitles": body.include_subtitles,
            "caption_style": caption_style,
            "caption_style_resolved": resolved_pack.id,
            "aspect_ratio": preset.id,
            "quality": quality,
            "width": render_w,
            "height": render_h,
            "crf": crf,
            "fps": fps,
            "x264_preset": x264_preset,
            "background_music_asset_id": str(body.background_music_asset_id)
            if body.background_music_asset_id
            else None,
            "background_music_volume": body.background_music_volume,
            "slide_id": str(body.slide_id) if body.slide_id else None,
            "slide_order": slides[0].order_index + 1 if single else None,
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
