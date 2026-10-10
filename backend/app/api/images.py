"""Queue Qwen-Image-2.1 stills for every story slide that has an image prompt."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.projects import get_owned_project
from app.db.models import Story, StoryJob, User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.services.music_job import latest_job
from app.services.stage_job import dispatch_stage_task, job_view
from app.utils.exceptions import AppError
from app.workers.tasks import generate_project_images

router = APIRouter(tags=["images"])


class ImageGenerateRequest(BaseModel):
    force: bool = False


def _job_out(job: StoryJob) -> dict:
    return job_view(job)


@router.get("/projects/{project_id}/images/job")
def image_job(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, project_id, user)
    job = latest_job(db, project.id, "images")
    return {"job": None if job is None else _job_out(job)}


@router.post("/projects/{project_id}/images/generate", status_code=202)
def generate_images(
    project_id: UUID,
    body: ImageGenerateRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    project = get_owned_project(db, project_id, user)
    story = db.scalar(select(Story).where(Story.project_id == project.id))
    if story is None:
        raise AppError("VALIDATION", "Generate a story before scene images", 400)
    active = db.scalar(
        select(StoryJob).where(
            StoryJob.project_id == project.id,
            StoryJob.stage == "images",
            StoryJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        return JSONResponse(_job_out(active), status_code=202)
    job = StoryJob(
        project_id=project.id,
        stage="images",
        status="queued",
        attempts=0,
        payload={"force": bool(body.force) if body is not None else False},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    dispatch_stage_task(db, job, lambda: generate_project_images.delay(str(job.id)))
    return JSONResponse(_job_out(job), status_code=202)
