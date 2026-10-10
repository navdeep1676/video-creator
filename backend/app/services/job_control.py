from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Project, Slide, VideoJob
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def render_job_is_stuck(
    started_at: datetime | None,
    heartbeat_at: datetime | None,
    now: datetime,
    *,
    stale_s: int,
    hard_limit_s: int,
) -> bool:
    """A live Wan render heartbeats on every step. Fail only a silent or runaway job."""
    now = _aware(now)
    last = heartbeat_at or started_at
    if last is None:
        return False
    if _aware(last) < now - timedelta(seconds=stale_s):
        return True
    if started_at is not None and _aware(started_at) < now - timedelta(seconds=hard_limit_s):
        return True
    return False


def revoke_celery_task(task_id: str | None, *, terminate: bool = True) -> bool:
    """Best-effort revoke of a Celery task. Returns True if an id was sent."""
    if not task_id:
        return False
    try:
        celery_app.control.revoke(task_id, terminate=terminate, signal="SIGTERM")
        logger.info("Revoked celery task %s (terminate=%s)", task_id, terminate)
        return True
    except Exception as e:
        logger.warning("Failed to revoke celery task %s: %s", task_id, e)
        return False


def cancel_video_job(db: Session, job: VideoJob) -> VideoJob:
    """Mark a video job cancelled and kill its worker task if running."""
    if job.status in {"completed", "failed", "cancelled"}:
        return job
    task_id = job.celery_task_id
    job.status = "cancelled"
    job.stage = "cancelled"
    job.error_code = "CANCELLED"
    job.error_message = "Cancelled by user"
    job.finished_at = utcnow()
    job.heartbeat_at = utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    revoke_celery_task(task_id, terminate=True)
    return job


def cancel_project_tts(db: Session, project: Project) -> dict:
    """
    Cancel all queued/processing TTS narrations for a project.
    Marks status cancelled and revokes known celery task ids.
    """
    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.project_id == project.id)
    ).all()
    cancelled = 0
    revoked = 0
    task_ids: list[str] = []
    for slide in slides:
        narr = slide.narration
        if not narr:
            continue
        if narr.tts_status not in {"queued", "processing"}:
            continue
        if narr.celery_task_id:
            task_ids.append(narr.celery_task_id)
        narr.tts_status = "cancelled"
        narr.tts_error = "Cancelled by user"
        narr.celery_task_id = None
        db.add(narr)
        cancelled += 1
    db.commit()
    for tid in task_ids:
        if revoke_celery_task(tid, terminate=True):
            revoked += 1
    return {"cancelled_tts": cancelled, "revoked_tasks": revoked}


def cancel_project_jobs(db: Session, project: Project) -> dict:
    """Stop TTS + active video renders for a project."""
    tts = cancel_project_tts(db, project)
    jobs = db.scalars(
        select(VideoJob).where(
            VideoJob.project_id == project.id,
            VideoJob.status.in_(["queued", "processing"]),
        )
    ).all()
    cancelled_jobs = 0
    for job in jobs:
        cancel_video_job(db, job)
        cancelled_jobs += 1
    return {**tts, "cancelled_renders": cancelled_jobs}