from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Narration, Project, Slide, User, VideoJob
from app.db.session import get_db
from app.dependencies import get_current_user
from app.schemas.common import ListResponse, ProjectCreate, ProjectOut, ProjectUpdate
from app.services.aspect_ratios import project_aspect_ratio, resolve_aspect_ratio
from app.utils.exceptions import AppError

router = APIRouter(prefix="/projects", tags=["projects"])


def get_owned_project(db: Session, project_id: UUID, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise AppError("NOT_FOUND", "Project not found", 404)
    return project


def _project_stats(db: Session, project_ids: list[UUID]) -> dict[UUID, dict]:
    if not project_ids:
        return {}
    stats: dict[UUID, dict] = {
        pid: {
            "slide_count": 0,
            "ready_audio_count": 0,
            "video_job_count": 0,
            "last_render_status": None,
        }
        for pid in project_ids
    }

    slide_rows = db.execute(
        select(Slide.project_id, func.count(Slide.id))
        .where(Slide.project_id.in_(project_ids))
        .group_by(Slide.project_id)
    ).all()
    for pid, count in slide_rows:
        stats[pid]["slide_count"] = int(count)

    ready_rows = db.execute(
        select(Slide.project_id, func.count(Narration.id))
        .join(Narration, Narration.slide_id == Slide.id)
        .where(Slide.project_id.in_(project_ids), Narration.tts_status == "ready")
        .group_by(Slide.project_id)
    ).all()
    for pid, count in ready_rows:
        stats[pid]["ready_audio_count"] = int(count)

    job_count_rows = db.execute(
        select(VideoJob.project_id, func.count(VideoJob.id))
        .where(VideoJob.project_id.in_(project_ids))
        .group_by(VideoJob.project_id)
    ).all()
    for pid, count in job_count_rows:
        stats[pid]["video_job_count"] = int(count)

    # Latest job per project
    for pid in project_ids:
        latest = db.scalar(
            select(VideoJob)
            .where(VideoJob.project_id == pid)
            .order_by(VideoJob.created_at.desc())
            .limit(1)
        )
        if latest:
            stats[pid]["last_render_status"] = latest.status

    return stats


def _to_out(project: Project, stats: dict | None = None) -> ProjectOut:
    preset = project_aspect_ratio(project.settings)
    base = ProjectOut.model_validate(project).model_copy(
        update={
            "aspect_ratio": preset.id,
            "canvas_width": preset.width,
            "canvas_height": preset.height,
        }
    )
    if stats:
        return base.model_copy(
            update={
                "slide_count": stats.get("slide_count", 0),
                "ready_audio_count": stats.get("ready_audio_count", 0),
                "video_job_count": stats.get("video_job_count", 0),
                "last_render_status": stats.get("last_render_status"),
            }
        )
    return base


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    try:
        preset = resolve_aspect_ratio(body.aspect_ratio)
    except ValueError as e:
        raise AppError("VALIDATION", str(e), 400) from e
    project = Project(
        owner_id=user.id,
        title=body.title.strip(),
        description=body.description,
        status="draft",
        settings={
            "aspect_ratio": preset.id,
            "canvas_width": preset.width,
            "canvas_height": preset.height,
        },
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_out(project)


@router.get("", response_model=ListResponse)
def list_projects(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str = Query("all"),
    q: str | None = Query(None, description="Search title/description"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListResponse:
    query = select(Project).where(Project.owner_id == user.id)
    if status != "all":
        query = query.where(Project.status == status)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            (Project.title.ilike(term)) | (Project.description.ilike(term))
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(db.scalars(query.order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all())
    stats = _project_stats(db, [p.id for p in items])
    return ListResponse(
        items=[_to_out(p, stats.get(p.id)) for p in items],
        total=total,
    )


@router.get("/summary")
def projects_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Dashboard aggregate stats for the current user."""
    projects = list(db.scalars(select(Project).where(Project.owner_id == user.id)).all())
    draft = sum(1 for p in projects if p.status == "draft")
    archived = sum(1 for p in projects if p.status == "archived")
    project_ids = [p.id for p in projects]
    stats = _project_stats(db, project_ids)
    slides = sum(s["slide_count"] for s in stats.values())
    ready = sum(s["ready_audio_count"] for s in stats.values())
    videos = sum(s["video_job_count"] for s in stats.values())
    completed_renders = 0
    if project_ids:
        completed_renders = (
            db.scalar(
                select(func.count(VideoJob.id)).where(
                    VideoJob.project_id.in_(project_ids),
                    VideoJob.status == "completed",
                )
            )
            or 0
        )
    return {
        "total_projects": len(projects),
        "draft_projects": draft,
        "archived_projects": archived,
        "total_slides": slides,
        "ready_audio": ready,
        "total_video_jobs": videos,
        "completed_renders": int(completed_renders),
        "storage_bytes": sum(p.storage_bytes or 0 for p in projects),
    }


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = get_owned_project(db, project_id, user)
    stats = _project_stats(db, [project.id]).get(project.id)
    return _to_out(project, stats)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = get_owned_project(db, project_id, user)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise AppError("VALIDATION", "Title cannot be empty", 400)
        project.title = title
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        if body.status not in {"draft", "archived"}:
            raise AppError("VALIDATION", "status must be draft or archived", 400)
        project.status = body.status
    if body.aspect_ratio is not None:
        slide_count = db.scalar(
            select(func.count(Slide.id)).where(Slide.project_id == project.id)
        ) or 0
        if slide_count > 0:
            raise AppError(
                "ASPECT_LOCKED",
                "Aspect ratio cannot change after slides are uploaded. Create a new project for a different format.",
                400,
            )
        try:
            preset = resolve_aspect_ratio(body.aspect_ratio)
        except ValueError as e:
            raise AppError("VALIDATION", str(e), 400) from e
        settings = dict(project.settings or {})
        settings["aspect_ratio"] = preset.id
        settings["canvas_width"] = preset.width
        settings["canvas_height"] = preset.height
        project.settings = settings
    db.add(project)
    db.commit()
    db.refresh(project)
    stats = _project_stats(db, [project.id]).get(project.id)
    return _to_out(project, stats)


@router.delete("/{project_id}")
def delete_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, project_id, user)
    db.delete(project)
    db.commit()
    return {"ok": True}
