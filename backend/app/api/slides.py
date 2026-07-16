from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.projects import get_owned_project
from app.config import get_settings
from app.db.models import Narration, Project, Slide, User
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import NarrationOut, ReorderRequest, SlideOut, SlideUpdate
from app.services.duration import effective_duration_ms
from app.services.media_tokens import signed_url_path
from app.services.storage import LocalStorage
from app.utils.exceptions import AppError
from app.utils.files import validate_image_bytes

router = APIRouter(tags=["slides"])


def _slide_out(slide: Slide, user_id: UUID) -> SlideOut:
    narr = slide.narration
    narr_out = None
    if narr:
        narr_out = NarrationOut(
            id=narr.id,
            text=narr.text,
            voice=narr.voice,
            speed=narr.speed,
            audio_key=narr.audio_key,
            audio_url=signed_url_path(narr.audio_key, str(user_id)) if narr.audio_key else None,
            tts_status=narr.tts_status,
            tts_error=narr.tts_error,
            audio_duration_ms=narr.audio_duration_ms,
        )
    return SlideOut(
        id=slide.id,
        project_id=slide.project_id,
        order_index=slide.order_index,
        image_key=slide.image_key,
        image_url=signed_url_path(slide.image_key, str(user_id)),
        duration_ms=slide.duration_ms,
        effective_duration_ms=effective_duration_ms(slide, narr),
        transition=slide.transition,
        animation=slide.animation,
        narration=narr_out,
    )


@router.post("/projects/{project_id}/slides", response_model=list[SlideOut])
async def upload_slides(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> list[SlideOut]:
    settings = get_settings()
    project = get_owned_project(db, project_id, user)
    existing_count = len(
        db.scalars(select(Slide).where(Slide.project_id == project.id)).all()
    )
    if existing_count + len(files) > settings.max_slides_per_project:
        raise AppError("SLIDE_LIMIT", f"Max {settings.max_slides_per_project} slides per project", 400)

    max_order = db.scalar(
        select(Slide.order_index).where(Slide.project_id == project.id).order_by(Slide.order_index.desc()).limit(1)
    )
    next_order = 0 if max_order is None else max_order + 1
    created: list[Slide] = []

    for f in files:
        data = await f.read()
        if len(data) > settings.max_image_bytes:
            raise AppError("FILE_TOO_LARGE", f"{f.filename} exceeds 10MB", 413)
        try:
            ext = validate_image_bytes(data, f.filename or "image.png")
        except ValueError as e:
            raise AppError("INVALID_IMAGE", str(e), 400) from e

        slide_id = uuid4()
        key = f"uploads/{project.id}/images/{slide_id}{ext}"
        storage.put_bytes(key, data)
        project.storage_bytes += len(data)

        slide = Slide(
            id=slide_id,
            project_id=project.id,
            order_index=next_order,
            image_key=key,
            duration_ms=settings.default_duration_ms,
            transition="fade",
            animation="none",
        )
        project_settings = project.settings or {}
        default_voice = (
            project_settings.get("default_voice")
            or settings.default_voice
        )
        narr = Narration(
            slide_id=slide_id,
            text="",
            voice=default_voice,
            speed=1.0,
            tts_status="missing",
        )
        db.add(slide)
        db.add(narr)
        created.append(slide)
        next_order += 1

    db.add(project)
    db.commit()
    # reload with narrations
    ids = [s.id for s in created]
    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.id.in_(ids)).order_by(Slide.order_index)
    ).all()
    return [_slide_out(s, user.id) for s in slides]


@router.get("/projects/{project_id}/slides", response_model=list[SlideOut])
def list_slides(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SlideOut]:
    project = get_owned_project(db, project_id, user)
    slides = db.scalars(
        select(Slide)
        .options(selectinload(Slide.narration))
        .where(Slide.project_id == project.id)
        .order_by(Slide.order_index)
    ).all()
    return [_slide_out(s, user.id) for s in slides]


@router.patch("/slides/{slide_id}", response_model=SlideOut)
def update_slide(
    slide_id: UUID,
    body: SlideUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> SlideOut:
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    project = get_owned_project(db, slide.project_id, user)
    narr = slide.narration
    if not narr:
        narr = Narration(slide_id=slide.id, text="", voice=get_settings().default_voice)
        db.add(narr)
        slide.narration = narr

    invalidate = False
    if body.text is not None and body.text != narr.text:
        narr.text = body.text
        invalidate = True
    if body.voice is not None and body.voice != narr.voice:
        narr.voice = body.voice
        invalidate = True
    if body.speed is not None and abs(body.speed - narr.speed) > 1e-6:
        narr.speed = body.speed
        invalidate = True
    if body.duration_ms is not None:
        slide.duration_ms = body.duration_ms
    if body.transition is not None:
        if body.transition not in {"none", "fade"}:
            raise AppError("VALIDATION", "transition must be none or fade", 400)
        slide.transition = body.transition
    if body.animation is not None:
        if body.animation not in {"none", "ken_burns"}:
            raise AppError("VALIDATION", "animation must be none or ken_burns", 400)
        slide.animation = body.animation

    if invalidate:
        if narr.audio_key and storage.exists(narr.audio_key):
            try:
                project.storage_bytes = max(0, project.storage_bytes - storage.size(narr.audio_key))
            except Exception:
                pass
            storage.delete(narr.audio_key)
        narr.audio_key = None
        narr.audio_duration_ms = None
        narr.tts_status = "missing"
        narr.tts_error = None

    db.add(slide)
    db.add(narr)
    db.add(project)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.delete("/slides/{slide_id}")
def delete_slide(
    slide_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> dict:
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    project = get_owned_project(db, slide.project_id, user)
    # free storage
    for key in [slide.image_key, slide.narration.audio_key if slide.narration else None]:
        if key and storage.exists(key):
            project.storage_bytes = max(0, project.storage_bytes - storage.size(key))
            storage.delete(key)
    db.delete(slide)
    db.add(project)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/slides/reorder", response_model=list[SlideOut])
def reorder_slides(
    project_id: UUID,
    body: ReorderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SlideOut]:
    project = (
        db.execute(select(Project).where(Project.id == project_id).with_for_update())
        .scalar_one_or_none()
    )
    if not project or project.owner_id != user.id:
        raise AppError("NOT_FOUND", "Project not found", 404)

    slides = db.scalars(select(Slide).where(Slide.project_id == project.id)).all()
    by_id = {s.id: s for s in slides}
    if set(body.slide_ids) != set(by_id.keys()) or len(body.slide_ids) != len(by_id):
        raise AppError("VALIDATION", "slide_ids must be a permutation of project slides", 400)

    # Phase 1: temporary negative indices
    for i, s in enumerate(slides):
        s.order_index = -(i + 1)
        db.add(s)
    db.flush()
    # Phase 2: final order
    for idx, sid in enumerate(body.slide_ids):
        by_id[sid].order_index = idx
        db.add(by_id[sid])
    db.commit()

    ordered = db.scalars(
        select(Slide)
        .options(selectinload(Slide.narration))
        .where(Slide.project_id == project.id)
        .order_by(Slide.order_index)
    ).all()
    return [_slide_out(s, user.id) for s in ordered]
