"""Claim and dispatch story, music, and image jobs that share the StoryJob table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StoryJob
from app.db.models.models import utcnow
from app.utils.exceptions import AppError

_START_DETAIL = {
    "story": "Waiting to start the story",
    "music": "Waiting to start the music",
    "images": "Waiting to start scene images",
}

ABANDONED_INLINE_JOB_S = 120
_INLINE_STAGES = frozenset({"story", "music"})


def claim_action(status: str, stored_task_id: str | None, task_id: str | None) -> str:
    """Decide whether this delivery should run a stage job.

    ``claim`` starts a queued job. ``resume`` continues the same Celery delivery
    after a crash. ``skip`` leaves the row alone.
    """
    if status == "queued":
        return "claim"
    if status == "running" and (not stored_task_id or stored_task_id == task_id):
        return "resume"
    return "skip"


def begin_stage_job(session: Session, job_id, task_id: str | None) -> StoryJob | None:
    """Lock the row and mark it running. Return None when another worker owns it."""
    job = session.scalar(select(StoryJob).where(StoryJob.id == job_id).with_for_update())
    if job is None:
        return None
    action = claim_action(job.status, job.celery_task_id, task_id)
    if action == "skip":
        session.rollback()
        return None
    if action == "claim":
        job.status = "running"
        job.attempts = (job.attempts or 0) + 1
        job.celery_task_id = task_id
        job.started_at = utcnow()
        if not job.detail:
            job.detail = _START_DETAIL.get(job.stage, "Starting")
    elif task_id and not job.celery_task_id:
        job.celery_task_id = task_id
    session.commit()
    return job


def report_progress(session: Session, job: StoryJob, progress: int, detail: str) -> None:
    """Save a percent and a short line so the UI can poll them."""
    job.progress = max(0, min(100, int(progress)))
    job.detail = (detail or "")[:500] or None
    if job.started_at is None:
        job.started_at = utcnow()
    session.add(job)
    session.commit()


def job_view(job: StoryJob) -> dict:
    progress = int(getattr(job, "progress", 0) or 0)
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "stage": job.stage,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
        "progress": progress,
        "detail": getattr(job, "detail", None),
        "started_at": getattr(job, "started_at", None),
        "created_at": getattr(job, "created_at", None),
    }


def is_abandoned_inline_job(
    *,
    stage: str,
    status: str,
    celery_task_id: str | None,
    created_at: datetime,
    now: datetime,
) -> bool:
    """Story and music rows left by the old in-process runner have no Celery id."""
    if stage not in _INLINE_STAGES or status not in {"queued", "running"} or celery_task_id:
        return False
    created = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
    return created < now - timedelta(seconds=ABANDONED_INLINE_JOB_S)


def dispatch_stage_task(db: Session, job: StoryJob, send) -> str:
    """Send a Celery task. A broker failure marks the row failed and raises AppError."""
    try:
        result = send()
    except Exception as exc:
        job.status = "failed"
        job.error = f"Could not queue the {job.stage} job: {exc}"
        db.add(job)
        db.commit()
        raise AppError("QUEUE", job.error, 503) from exc
    db.expire(job)
    job.celery_task_id = result.id
    db.commit()
    return result.id
