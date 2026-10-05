from __future__ import annotations

from uuid import UUID

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    MusicAsset,
    Narration,
    Project,
    Slide,
    Story,
    StoryCharacter,
    StoryJob,
    StoryLocation,
    StoryScene,
    User,
    VideoJob,
)
from app.db.session import get_db
from app.dependencies import get_current_user
from app.services.media_tokens import signed_url_path
from app.services.music_job import latest_job, music_storage_key
from app.services.openrouter_catalog import load_catalog
from app.services.story_job import build_llm_provider, execute_story_job, latest_story_job
from app.services.story_slides import replace_project_slides
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


class StoryRequest(BaseModel):
    content_type: Literal["horror", "kids"] = "horror"
    topic: str = Field(min_length=1, max_length=4000)
    duration_seconds: int = Field(ge=5, le=7200)
    language: Literal["en", "hi", "hinglish"] = "en"
    visual_style: str = Field(default="Dark Horror", max_length=80)
    voice: str = Field(default="female", max_length=32)
    music_mode: Literal["none", "background", "full_song"] = "background"
    scene_count: str = "auto"
    llm_model: str | None = None


def _check_scene_count(value: str) -> str:
    if value == "auto":
        return value
    if value.isdigit() and 1 <= int(value) <= 300:
        return value
    raise AppError("VALIDATION", "scene_count must be auto or an integer from 1 to 300", 400)


def _job_out(job: StoryJob) -> dict:
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "stage": job.stage,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
    }


def _character_out(row: StoryCharacter) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "age": row.age,
        "appearance": row.appearance,
        "clothing": row.clothing,
        "personality": row.personality,
        "style": row.style,
        "seed": row.seed,
    }


def _location_out(row: StoryLocation) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "lighting": row.lighting,
        "mood": row.mood,
    }


def _attach_scene_music(scenes: list[dict], plan: dict) -> None:
    planned = plan.get("scenes") if isinstance(plan.get("scenes"), list) else []
    for scene in scenes:
        index = scene.get("index")
        draft = planned[index] if isinstance(index, int) and 0 <= index < len(planned) and isinstance(planned[index], dict) else {}
        scene["music_prompt"] = str(draft.get("music_prompt") or "")


def _scene_out(
    scene: StoryScene,
    characters_by_id: dict[str, StoryCharacter],
    locations_by_id: dict[str, StoryLocation],
) -> dict:
    names: list[str] = []
    for raw in scene.character_ids or []:
        row = characters_by_id.get(str(raw))
        if row is not None:
            names.append(row.name)
    location = locations_by_id.get(str(scene.location_id)) if scene.location_id else None
    return {
        "id": str(scene.id),
        "index": scene.index,
        "beat": scene.beat,
        "narration": scene.narration,
        "dialogue": scene.dialogue or "",
        "duration": scene.duration,
        "start_time": scene.start_time,
        "end_time": scene.end_time,
        "generation_mode": scene.generation_mode,
        "status": scene.status,
        "image_prompt": scene.image_prompt or "",
        "video_prompt": scene.video_prompt or "",
        "camera_motion": scene.camera_motion or "",
        "transition": scene.transition or "",
        "sfx": list(scene.sfx or []),
        "characters": names,
        "location": "" if location is None else location.name,
    }


def _plan_document(
    story: Story | None,
    characters: list[StoryCharacter],
    locations: list[StoryLocation],
    scenes: list[dict],
) -> dict:
    if story is not None and isinstance(story.plan, dict) and story.plan:
        return story.plan
    if story is None:
        return {}
    return {
        "title": story.title,
        "hook": story.hook,
        "story": story.body,
        "lyrics": story.lyrics,
        "kids_format": None,
        "characters": [_character_out(row) for row in characters],
        "locations": [_location_out(row) for row in locations],
        "music_prompt": "",
        "sfx_notes": "",
        "scenes": scenes,
    }


@router.get("/{project_id}/story")
def get_story(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, project_id, user)
    story = db.scalar(select(Story).where(Story.project_id == project.id))
    characters = list(
        db.scalars(
            select(StoryCharacter)
            .where(StoryCharacter.project_id == project.id)
            .order_by(StoryCharacter.name)
        ).all()
    )
    locations = list(
        db.scalars(
            select(StoryLocation).where(StoryLocation.project_id == project.id).order_by(StoryLocation.name)
        ).all()
    )
    scene_rows = list(
        db.scalars(select(StoryScene).where(StoryScene.project_id == project.id).order_by(StoryScene.index)).all()
    )
    characters_by_id = {str(row.id): row for row in characters}
    locations_by_id = {str(row.id): row for row in locations}
    scenes = [_scene_out(scene, characters_by_id, locations_by_id) for scene in scene_rows]
    plan = _plan_document(story, characters, locations, scenes)
    _attach_scene_music(scenes, plan)
    job = latest_story_job(db, project.id)
    music_job = latest_job(db, project.id, "music")
    image_job = latest_job(db, project.id, "images")
    music_key = music_storage_key(project.id)
    music_asset = db.scalar(
        select(MusicAsset).where(MusicAsset.project_id == project.id, MusicAsset.storage_key == music_key)
    )
    return {
        "settings": (project.settings or {}).get("story"),
        "job": None if job is None else _job_out(job),
        "music": {
            "job": None if music_job is None else _job_out(music_job),
            "audio_url": signed_url_path(music_key, str(user.id)) if music_asset is not None else None,
            "filename": None if music_asset is None else music_asset.filename,
        },
        "images": {"job": None if image_job is None else _job_out(image_job)},
        "story": None
        if story is None
        else {
            "title": story.title,
            "hook": story.hook,
            "body": story.body,
            "lyrics": story.lyrics,
            "kids_format": plan.get("kids_format"),
            "music_prompt": plan.get("music_prompt") or "",
            "sfx_notes": plan.get("sfx_notes") or "",
            "plan": plan,
        },
        "characters": [_character_out(row) for row in characters],
        "locations": [_location_out(row) for row in locations],
        "scenes": scenes,
    }


@router.post("/{project_id}/story/slides")
def build_story_slides(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Replace project slides with one slide per saved story scene."""
    project = get_owned_project(db, project_id, user)
    scene_rows = list(
        db.scalars(select(StoryScene).where(StoryScene.project_id == project.id).order_by(StoryScene.index)).all()
    )
    if not scene_rows:
        raise AppError("VALIDATION", "Generate a story before creating slides", 400)
    count = replace_project_slides(db, project, scene_rows)
    db.commit()
    return {"slides": count}


@router.post("/{project_id}/story", status_code=202)
def enqueue_story(
    project_id: UUID,
    body: StoryRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, project_id, user)
    scene_count = _check_scene_count(body.scene_count.strip())
    settings = get_settings()
    catalog = load_catalog(settings)
    model = body.llm_model or settings.openrouter_model
    if model not in catalog.ids():
        raise AppError("VALIDATION", "Choose a free text model from the catalog", 400)
    active = db.scalar(
        select(StoryJob).where(
            StoryJob.project_id == project.id,
            StoryJob.stage == "story",
            StoryJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        return _job_out(active)
    payload = body.model_dump()
    payload["scene_count"] = scene_count
    payload["llm_model"] = model
    job = StoryJob(project_id=project.id, stage="story", status="queued", attempts=0, payload=payload)
    stored = dict(project.settings or {})
    stored["story"] = payload
    project.settings = stored
    db.add(job)
    db.commit()
    db.refresh(job)
    provider = build_llm_provider(settings, model, getattr(request.app.state, "llm_provider", None))
    background.add_task(execute_story_job, job.id, provider)
    return _job_out(job)
