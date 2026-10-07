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
from app.schemas.common import (
    CreateSlideRequest,
    NarrationOut,
    ReorderImagesRequest,
    ReorderRequest,
    SlideImageOut,
    SlideImageUpdate,
    SlideImagesDurationsUpdate,
    SlideOut,
    SlideUpdate,
)
from app.services.aspect_ratios import project_aspect_ratio
from app.services.duration import effective_duration_ms
from app.services.story_slides import align_story_slide_durations
from app.services.image_fit import fit_image_to_aspect
from app.services.media_tokens import signed_url_path
from app.services.storage import LocalStorage
from app.utils.exceptions import AppError
from app.utils.files import validate_image_bytes

router = APIRouter(tags=["slides"])


def _slide_images_out(slide: Slide, user_id: UUID) -> list[SlideImageOut]:
    entries = slide.all_image_entries()
    n = len(entries)
    # Default equal share of effective slide duration when duration not set
    effective = effective_duration_ms(slide, slide.narration)
    equal = max(100, effective // n) if n else 0
    return [
        SlideImageOut(
            index=i,
            image_key=e["key"],
            image_url=signed_url_path(e["key"], str(user_id)),
            duration_ms=e["duration_ms"] if e.get("duration_ms") is not None else equal,
        )
        for i, e in enumerate(entries)
    ]


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
    images = _slide_images_out(slide, user_id)
    cover = images[0].image_url if images else None
    cover_key = images[0].image_key if images else None
    return SlideOut(
        id=slide.id,
        project_id=slide.project_id,
        order_index=slide.order_index,
        image_key=cover_key,
        image_url=cover,
        images=images,
        image_count=len(images),
        duration_ms=slide.duration_ms,
        effective_duration_ms=effective_duration_ms(slide, narr),
        transition=slide.transition,
        animation=slide.animation,
        motion_prompt=slide.motion_prompt,
        narration=narr_out,
    )


VALID_ANIMATIONS = frozenset({"none", "ken_burns", "wan_i2v", "wan_t2v"})
_ANIMATION_ERROR = "animation must be none, ken_burns, wan_i2v, or wan_t2v"


def _default_voice(project: Project) -> str:
    settings = get_settings()
    project_settings = project.settings or {}
    return project_settings.get("default_voice") or settings.default_voice


def _next_order(db: Session, project_id: UUID) -> int:
    max_order = db.scalar(
        select(Slide.order_index)
        .where(Slide.project_id == project_id)
        .order_by(Slide.order_index.desc())
        .limit(1)
    )
    return 0 if max_order is None else max_order + 1


def _validate_and_store_image(
    *,
    data: bytes,
    name: str,
    project: Project,
    preset,
    storage: LocalStorage,
    settings,
) -> str:
    """Validate image type, scale+pad to project canvas (no crop), store."""
    if len(data) > settings.max_image_bytes:
        raise AppError("FILE_TOO_LARGE", f"{name} exceeds 10MB", 413)
    try:
        ext = validate_image_bytes(data, name)
    except ValueError as e:
        raise AppError("INVALID_IMAGE", str(e), 400) from e

    try:
        fitted = fit_image_to_aspect(
            data,
            preset,
            preferred_ext=ext,
            max_long_edge=max(preset.width, preset.height),
        )
    except Exception as e:
        raise AppError("INVALID_IMAGE", f"{name}: could not process image ({e})", 400) from e

    # Prefer fitted extension (JPEG after crop is common)
    out_ext = fitted.ext if fitted.ext.startswith(".") else f".{fitted.ext}"
    if out_ext == ".jpeg":
        out_ext = ".jpg"
    key = f"uploads/{project.id}/images/{uuid4()}{out_ext}"
    storage.put_bytes(key, fitted.data)
    project.storage_bytes += len(fitted.data)
    return key


@router.post("/projects/{project_id}/slides/create", response_model=SlideOut)
def create_empty_slide(
    project_id: UUID,
    body: CreateSlideRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlideOut:
    """Create a slide shell (no images yet). Add images with POST /slides/{id}/images."""
    settings = get_settings()
    body = body or CreateSlideRequest()
    project = get_owned_project(db, project_id, user)
    existing_count = len(db.scalars(select(Slide).where(Slide.project_id == project.id)).all())
    if existing_count + 1 > settings.max_slides_per_project:
        raise AppError("SLIDE_LIMIT", f"Max {settings.max_slides_per_project} slides per project", 400)

    if body.transition not in {"none", "fade"}:
        raise AppError("VALIDATION", "transition must be none or fade", 400)
    if body.animation not in VALID_ANIMATIONS:
        raise AppError(
            "VALIDATION",
            _ANIMATION_ERROR,
            400,
        )

    slide_id = uuid4()
    slide = Slide(
        id=slide_id,
        project_id=project.id,
        order_index=_next_order(db, project.id),
        image_key=None,
        image_keys=[],
        duration_ms=settings.default_duration_ms,
        transition=body.transition,
        animation=body.animation,
        motion_prompt=(body.motion_prompt or "").strip() or None,
    )
    narr = Narration(
        slide_id=slide_id,
        text="",
        voice=_default_voice(project),
        speed=1.0,
        tts_status="missing",
    )
    db.add(slide)
    db.add(narr)
    db.commit()
    slide = db.scalar(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id)
    )
    assert slide is not None
    return _slide_out(slide, user.id)


@router.post("/projects/{project_id}/slides", response_model=list[SlideOut])
async def upload_slides(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> list[SlideOut]:
    """Upload images as new slides (one image → one slide each)."""
    settings = get_settings()
    project = get_owned_project(db, project_id, user)
    preset = project_aspect_ratio(project.settings)
    existing_count = len(db.scalars(select(Slide).where(Slide.project_id == project.id)).all())
    if existing_count + len(files) > settings.max_slides_per_project:
        raise AppError("SLIDE_LIMIT", f"Max {settings.max_slides_per_project} slides per project", 400)

    next_order = _next_order(db, project.id)
    created: list[Slide] = []

    for f in files:
        data = await f.read()
        name = f.filename or "image.png"
        key = _validate_and_store_image(
            data=data,
            name=name,
            project=project,
            preset=preset,
            storage=storage,
            settings=settings,
        )
        slide_id = uuid4()
        slide = Slide(
            id=slide_id,
            project_id=project.id,
            order_index=next_order,
            image_key=key,
            image_keys=[{"key": key, "duration_ms": settings.default_duration_ms}],
            duration_ms=settings.default_duration_ms,
            transition="fade",
            animation="none",
        )
        narr = Narration(
            slide_id=slide_id,
            text="",
            voice=_default_voice(project),
            speed=1.0,
            tts_status="missing",
        )
        db.add(slide)
        db.add(narr)
        created.append(slide)
        next_order += 1

    db.add(project)
    db.commit()
    ids = [s.id for s in created]
    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.id.in_(ids)).order_by(Slide.order_index)
    ).all()
    return [_slide_out(s, user.id) for s in slides]


@router.post("/slides/{slide_id}/images", response_model=SlideOut)
async def add_images_to_slide(
    slide_id: UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> SlideOut:
    """Append one or more images to an existing slide (slideshow within that slide)."""
    settings = get_settings()
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    project = get_owned_project(db, slide.project_id, user)
    preset = project_aspect_ratio(project.settings)

    if not files:
        raise AppError("VALIDATION", "No files uploaded", 400)

    entries = slide.all_image_entries()
    if len(entries) + len(files) > settings.max_images_per_slide:
        raise AppError(
            "IMAGE_LIMIT",
            f"Max {settings.max_images_per_slide} images per slide",
            400,
        )

    # Default new image duration: equal share of current effective duration
    effective = effective_duration_ms(slide, slide.narration)
    default_dur = max(500, effective // max(1, len(entries) + len(files)))

    for f in files:
        data = await f.read()
        name = f.filename or "image.png"
        key = _validate_and_store_image(
            data=data,
            name=name,
            project=project,
            preset=preset,
            storage=storage,
            settings=settings,
        )
        entries.append({"key": key, "duration_ms": default_dur})

    slide.set_image_entries(entries)
    db.add(slide)
    db.add(project)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.patch("/slides/{slide_id}/images/{image_index}", response_model=SlideOut)
def update_slide_image(
    slide_id: UUID,
    image_index: int,
    body: SlideImageUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlideOut:
    """Update per-image duration (ms) on a multi-image slide."""
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    entries = slide.all_image_entries()
    if image_index < 0 or image_index >= len(entries):
        raise AppError("NOT_FOUND", f"Image index {image_index} out of range", 404)
    if body.duration_ms is not None:
        entries[image_index]["duration_ms"] = body.duration_ms
    slide.set_image_entries(entries)
    db.add(slide)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.patch("/slides/{slide_id}/images", response_model=SlideOut)
def update_slide_image_durations(
    slide_id: UUID,
    body: SlideImagesDurationsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlideOut:
    """Batch-update image durations; optional equal-distribute when items empty with ?equal=true handled client-side."""
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    entries = slide.all_image_entries()
    for item in body.items or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(entries):
            raise AppError("VALIDATION", f"Image index {idx} out of range", 400)
        if "duration_ms" not in item:
            continue
        dur = item.get("duration_ms")
        if dur is None:
            entries[idx]["duration_ms"] = None
        else:
            try:
                d = int(dur)
            except (TypeError, ValueError) as e:
                raise AppError("VALIDATION", f"Invalid duration_ms for index {idx}", 400) from e
            if d < 100 or d > 120_000:
                raise AppError("VALIDATION", "duration_ms must be 100–120000", 400)
            entries[idx]["duration_ms"] = d
    slide.set_image_entries(entries)
    db.add(slide)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.post("/slides/{slide_id}/images/distribute", response_model=SlideOut)
def distribute_image_durations(
    slide_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlideOut:
    """Evenly split the slide's effective duration across all images."""
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    entries = slide.all_image_entries()
    if not entries:
        raise AppError("VALIDATION", "Slide has no images", 400)
    total = effective_duration_ms(slide, slide.narration)
    n = len(entries)
    base = max(100, total // n)
    rem = max(0, total - base * n)
    for i, e in enumerate(entries):
        e["duration_ms"] = base + (rem if i == n - 1 else 0)
    slide.set_image_entries(entries)
    db.add(slide)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.delete("/slides/{slide_id}/images/{image_index}", response_model=SlideOut)
def remove_image_from_slide(
    slide_id: UUID,
    image_index: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> SlideOut:
    """Remove one image from a slide by zero-based index."""
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    project = get_owned_project(db, slide.project_id, user)
    entries = slide.all_image_entries()
    if image_index < 0 or image_index >= len(entries):
        raise AppError("NOT_FOUND", f"Image index {image_index} out of range", 404)

    removed = entries.pop(image_index)
    key = removed.get("key")
    if key and storage.exists(key):
        project.storage_bytes = max(0, project.storage_bytes - storage.size(key))
        storage.delete(key)

    slide.set_image_entries(entries)
    db.add(slide)
    db.add(project)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.post("/slides/{slide_id}/images/reorder", response_model=SlideOut)
def reorder_slide_images(
    slide_id: UUID,
    body: ReorderImagesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlideOut:
    """Reorder images within a slide."""
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    entries = slide.all_image_entries()
    n = len(entries)
    if sorted(body.image_indices) != list(range(n)):
        raise AppError("VALIDATION", "image_indices must be a permutation of current image indices", 400)
    slide.set_image_entries([entries[i] for i in body.image_indices])
    db.add(slide)
    db.commit()
    db.refresh(slide)
    return _slide_out(slide, user.id)


@router.get("/projects/{project_id}/slides", response_model=list[SlideOut])
def list_slides(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SlideOut]:
    project = get_owned_project(db, project_id, user)
    if align_story_slide_durations(db, project.id):
        db.commit()
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
        if body.animation not in VALID_ANIMATIONS:
            raise AppError(
                "VALIDATION",
                _ANIMATION_ERROR,
                400,
            )
        slide.animation = body.animation
    if body.motion_prompt is not None:
        slide.motion_prompt = body.motion_prompt.strip() or None

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
    keys = slide.all_image_keys()
    if slide.narration and slide.narration.audio_key:
        keys = keys + [slide.narration.audio_key]
    for key in keys:
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

    for i, s in enumerate(slides):
        s.order_index = -(i + 1)
        db.add(s)
    db.flush()
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
