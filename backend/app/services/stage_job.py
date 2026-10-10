"""Claim and dispatch story, music, and image jobs that share the StoryJob table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StoryJob
from app.utils.exceptions import AppError

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
    elif task_id and not job.celery_task_id:
        job.celery_task_id = task_id
    session.commit()
    return job


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
