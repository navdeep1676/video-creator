from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Narration, Project, Slide, User
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import ProjectOut
from app.services.clipper import (
    bulk_update_frames,
    create_session_from_upload,
    delete_session,
    estimate_frame_count,
    extract_frames,
    load_session,
)
from app.services.media_tokens import signed_url_path
from app.services.storage import LocalStorage
from app.utils.exceptions import AppError
from app.utils.files import validate_video_bytes
from app.workers.tasks import generate_slide_tts

router = APIRouter(prefix="/clipper", tags=["clipper"])


class ExtractRequest(BaseModel):
    interval_s: float = Field(default=3.0, ge=0.5, le=60.0)
    max_frames: int = Field(default=30, ge=1, le=50)
    timestamps_s: list[float] | None = None


class FrameUpdate(BaseModel):
    frame_id: str
    selected: bool | None = None
    narration: str | None = None


class FramesUpdateRequest(BaseModel):
    frames: list[FrameUpdate]


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    frame_ids: list[str] | None = None  # default: all selected
    generate_tts: bool = False
    voice: str | None = None


def _frame_out(frame, user_id: UUID) -> dict:
    return {
        "id": frame.id,
        "time_ms": frame.time_ms,
        "time_label": _fmt_time(frame.time_ms),
        "image_key": frame.image_key,
        "image_url": signed_url_path(frame.image_key, str(user_id)),
        "selected": frame.selected,
        "narration": frame.narration,
    }


def _fmt_time(ms: int) -> str:
    s = max(0, ms) // 1000
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _session_out(session, user_id: UUID) -> dict:
    settings = get_settings()
    return {
        "id": session.id,
        "filename": session.filename,
        "duration_ms": session.duration_ms,
        "duration_label": _fmt_time(session.duration_ms),
        "created_at": session.created_at,
        "video_url": signed_url_path(session.video_key, str(user_id)),
        "frame_count": len(session.frames),
        "selected_count": sum(1 for f in session.frames if f.selected),
        "max_frames": settings.max_clipper_frames,
        "frames": [_frame_out(f, user_id) for f in session.frames],
    }


def _get_owned_session(user: User, session_id: str):
    session = load_session(str(user.id), session_id)
    if not session:
        raise AppError("NOT_FOUND", "Clipper session not found", 404)
    return session


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    storage: LocalStorage = Depends(get_storage_dep),
) -> dict:
    settings = get_settings()
    data = await file.read()
    if not data:
        raise AppError("VALIDATION", "Empty file", 400)
    if len(data) > settings.max_video_upload_bytes:
        raise AppError("FILE_TOO_LARGE", "Video exceeds 200MB limit", 413)
    try:
        ext = validate_video_bytes(data, file.filename or "video.mp4")
    except ValueError as e:
        raise AppError("INVALID_VIDEO", str(e), 400) from e

    try:
        session = create_session_from_upload(
            str(user.id),
            file.filename or f"video{ext}",
            data,
            ext,
            storage,
        )
    except ValueError as e:
        raise AppError("VALIDATION", str(e), 400) from e
    except RuntimeError as e:
        raise AppError("VIDEO_PROBE_FAILED", str(e), 400) from e

    return {
        "session": _session_out(session, user.id),
        "suggested_interval_s": 3.0,
        "estimated_frames_at_3s": estimate_frame_count(session.duration_ms, 3.0, settings.max_clipper_frames),
    }


@router.get("/{session_id}")
def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    session = _get_owned_session(user, session_id)
    return _session_out(session, user.id)


@router.post("/{session_id}/extract")
def extract(
    session_id: str,
    body: ExtractRequest,
    user: User = Depends(get_current_user),
    storage: LocalStorage = Depends(get_storage_dep),
) -> dict:
    session = _get_owned_session(user, session_id)
    settings = get_settings()
    max_frames = min(body.max_frames, settings.max_clipper_frames)
    try:
        session = extract_frames(
            session,
            interval_s=body.interval_s,
            max_frames=max_frames,
            timestamps_s=body.timestamps_s,
            storage=storage,
        )
    except FileNotFoundError as e:
        raise AppError("NOT_FOUND", str(e), 404) from e
    except Exception as e:
        raise AppError("EXTRACT_FAILED", f"Frame extraction failed: {e}", 500) from e
    return _session_out(session, user.id)


@router.patch("/{session_id}/frames")
def update_frames(
    session_id: str,
    body: FramesUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict:
    session = _get_owned_session(user, session_id)
    updates = [u.model_dump() for u in body.frames]
    session = bulk_update_frames(session, updates)
    return _session_out(session, user.id)


@router.post("/{session_id}/create-project", response_model=dict)
def create_project_from_clips(
    session_id: str,
    body: CreateProjectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> dict:
    """Turn selected clipper frames into a learning project (slides + narration), ready for voiceover."""
    settings = get_settings()
    session = _get_owned_session(user, session_id)
    if not session.frames:
        raise AppError("VALIDATION", "Extract frames first", 400)

    if body.frame_ids:
        id_set = set(body.frame_ids)
        frames = [f for f in session.frames if f.id in id_set]
    else:
        frames = [f for f in session.frames if f.selected]

    if not frames:
        raise AppError("VALIDATION", "Select at least one frame", 400)
    if len(frames) > settings.max_slides_per_project:
        raise AppError("SLIDE_LIMIT", f"Max {settings.max_slides_per_project} slides per project", 400)

    # Preserve chronological order
    frames = sorted(frames, key=lambda f: f.time_ms)
    voice = body.voice or settings.default_voice

    project = Project(
        owner_id=user.id,
        title=body.title.strip(),
        description=body.description
        or f"Clipped from {session.filename} ({len(frames)} frames)",
        status="draft",
    )
    db.add(project)
    db.flush()

    created_slide_ids: list[str] = []
    total_bytes = 0
    for order, frame in enumerate(frames):
        if not storage.exists(frame.image_key):
            raise AppError("NOT_FOUND", f"Frame image missing at {frame.time_ms}ms", 404)
        data = storage.get_bytes(frame.image_key)
        slide_id = uuid4()
        dest_key = f"uploads/{project.id}/images/{slide_id}.jpg"
        storage.put_bytes(dest_key, data)
        total_bytes += len(data)

        slide = Slide(
            id=slide_id,
            project_id=project.id,
            order_index=order,
            image_key=dest_key,
            image_keys=[{"key": dest_key, "duration_ms": settings.default_duration_ms}],
            duration_ms=settings.default_duration_ms,
            transition="fade",
            animation="ken_burns",
        )
        narr = Narration(
            slide_id=slide_id,
            text=(frame.narration or "").strip(),
            voice=voice,
            speed=1.0,
            tts_status="missing",
        )
        db.add(slide)
        db.add(narr)
        created_slide_ids.append(str(slide_id))

    project.storage_bytes = total_bytes
    db.add(project)
    db.commit()
    db.refresh(project)

    tts_enqueued = 0
    if body.generate_tts:
        for sid in created_slide_ids:
            narr = db.scalar(select(Narration).where(Narration.slide_id == UUID(sid)))
            if narr and (narr.text or "").strip():
                narr.tts_status = "queued"
                db.add(narr)
                generate_slide_tts.delay(sid, force=False)
                tts_enqueued += 1
        db.commit()

    return {
        "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        "project_id": str(project.id),
        "slide_count": len(created_slide_ids),
        "tts_enqueued": tts_enqueued,
        "editor_path": f"/projects/{project.id}",
    }


@router.delete("/{session_id}")
def remove_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    session = load_session(str(user.id), session_id)
    if session:
        delete_session(str(user.id), session_id)
    return {"ok": True}
