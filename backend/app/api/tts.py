from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.projects import get_owned_project
from app.db.models import Narration, Slide, User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.config import get_settings
from app.schemas.common import (
    ApplyLanguageRequest,
    LanguageOut,
    TTSBatchRequest,
    TTSCancelRequest,
    TTSGenerateRequest,
    TTSProviderOut,
    TTSProvidersStatusOut,
    TTSStatusOut,
    VoiceOut,
)
from app.services.job_control import cancel_project_tts
from app.services.media_tokens import signed_url_path
from app.services.storage import get_storage
from app.services.voices import (
    VOICE_IDS,
    default_voice_for_language,
    get_voice,
    list_languages,
    list_voices,
    public_voice,
    tts_provider_status,
)
from app.utils.exceptions import AppError
from app.workers.tasks import generate_slide_tts

router = APIRouter(prefix="/tts", tags=["tts"])


@router.get("/providers", response_model=TTSProvidersStatusOut)
def get_providers() -> TTSProvidersStatusOut:
    settings = get_settings()
    status = tts_provider_status(bool(settings.deepgram_api_key))
    return TTSProvidersStatusOut(
        deepgram_available=status["deepgram_available"],
        edge_available=status["edge_available"],
        providers=[TTSProviderOut(**p) for p in status["providers"]],
    )


@router.get("/languages", response_model=list[LanguageOut])
def get_languages() -> list[LanguageOut]:
    return [LanguageOut(**lang) for lang in list_languages()]


@router.get("/voices", response_model=list[VoiceOut])
def get_voices(
    language: str | None = Query(default=None),
    provider: str | None = Query(default=None, description="deepgram | edge | omit for all"),
) -> list[VoiceOut]:
    settings = get_settings()
    deepgram_ok = bool(settings.deepgram_api_key)
    voices = list_voices(language=language, provider=provider)
    return [VoiceOut(**public_voice(v, deepgram_available=deepgram_ok)) for v in voices]


@router.post("/apply-language")
def apply_language(
    body: ApplyLanguageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Set language voice on every slide in a project.
    Optionally enqueue TTS regeneration for slides that already have narration text.
    """
    project = get_owned_project(db, body.project_id, user)
    lang = body.language.strip().lower()
    available = {lang_item["code"] for lang_item in list_languages()}
    if lang not in available:
        raise AppError("VALIDATION", f"Unsupported language: {body.language}", 400)

    if body.voice:
        meta = get_voice(body.voice)
        if not meta or meta["language"] != lang:
            raise AppError("VALIDATION", "voice does not match language", 400)
        voice_id = body.voice
    else:
        voice_id = default_voice_for_language(lang)

    storage = get_storage()
    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.project_id == project.id)
    ).all()

    updated = 0
    enqueued = 0
    for slide in slides:
        narr = slide.narration
        if not narr:
            continue
        if narr.voice == voice_id and not body.regenerate:
            continue

        # Changing voice invalidates existing audio
        if narr.audio_key and storage.exists(narr.audio_key):
            try:
                project.storage_bytes = max(0, project.storage_bytes - storage.size(narr.audio_key))
            except Exception:
                pass
            storage.delete(narr.audio_key)
            # drop cue sidecar if present
            cues = storage.absolute_path(narr.audio_key).with_suffix(".cues.json")
            if cues.is_file():
                cues.unlink(missing_ok=True)

        narr.voice = voice_id
        narr.audio_key = None
        narr.audio_duration_ms = None
        narr.tts_status = "missing"
        narr.tts_error = None
        db.add(narr)
        updated += 1

        if body.regenerate and (narr.text or "").strip():
            narr.tts_status = "queued"
            db.add(narr)
            async_result = generate_slide_tts.delay(str(slide.id), force=True)
            narr.celery_task_id = async_result.id
            db.add(narr)
            enqueued += 1

    db.add(project)
    # Remember project default language
    settings = dict(project.settings or {})
    settings["language"] = lang
    settings["default_voice"] = voice_id
    project.settings = settings
    db.add(project)
    db.commit()
    return {
        "language": lang,
        "voice": voice_id,
        "updated": updated,
        "enqueued": enqueued,
    }


@router.post("/generate", response_model=TTSStatusOut)
def generate_tts(
    body: TTSGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TTSStatusOut:
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == body.slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    narr = slide.narration
    if not narr or not (narr.text or "").strip():
        raise AppError("VALIDATION", "Narration text is required", 400)
    if narr.voice not in VOICE_IDS:
        raise AppError("VALIDATION", f"Unsupported voice: {narr.voice}", 400)
    if narr.tts_status == "ready" and not body.force:
        return TTSStatusOut(
            slide_id=slide.id,
            tts_status=narr.tts_status,
            audio_url=signed_url_path(narr.audio_key, str(user.id)) if narr.audio_key else None,
            audio_duration_ms=narr.audio_duration_ms,
            tts_error=narr.tts_error,
        )
    if narr.tts_status in {"queued", "processing"} and not body.force:
        return TTSStatusOut(
            slide_id=slide.id,
            tts_status=narr.tts_status,
            audio_url=None,
            audio_duration_ms=narr.audio_duration_ms,
            tts_error=None,
        )

    narr.tts_status = "queued"
    narr.tts_error = None
    db.add(narr)
    db.commit()

    async_result = generate_slide_tts.delay(str(slide.id), force=body.force)
    narr.celery_task_id = async_result.id
    db.add(narr)
    db.commit()
    return TTSStatusOut(slide_id=slide.id, tts_status="queued", audio_url=None, audio_duration_ms=None, tts_error=None)


@router.post("/generate-batch")
def generate_batch(
    body: TTSBatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = get_owned_project(db, body.project_id, user)
    slides = db.scalars(
        select(Slide).options(selectinload(Slide.narration)).where(Slide.project_id == project.id)
    ).all()
    enqueued = 0
    for slide in slides:
        narr = slide.narration
        if not narr or not (narr.text or "").strip():
            continue
        if narr.tts_status == "ready" and not body.force:
            continue
        if narr.tts_status in {"queued", "processing"} and not body.force:
            continue
        if narr.voice not in VOICE_IDS:
            continue
        narr.tts_status = "queued"
        narr.tts_error = None
        db.add(narr)
        async_result = generate_slide_tts.delay(str(slide.id), force=body.force)
        narr.celery_task_id = async_result.id
        db.add(narr)
        enqueued += 1
    db.commit()
    return {"enqueued": enqueued}


@router.post("/cancel")
def cancel_tts(
    body: TTSCancelRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Stop all queued/processing voice-generation jobs for a project."""
    project = get_owned_project(db, body.project_id, user)
    result = cancel_project_tts(db, project)
    return {"ok": True, **result}


@router.get("/{slide_id}", response_model=TTSStatusOut)
def tts_status(
    slide_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TTSStatusOut:
    slide = db.scalar(select(Slide).options(selectinload(Slide.narration)).where(Slide.id == slide_id))
    if not slide:
        raise AppError("NOT_FOUND", "Slide not found", 404)
    get_owned_project(db, slide.project_id, user)
    narr = slide.narration
    if not narr:
        return TTSStatusOut(slide_id=slide_id, tts_status="missing")
    return TTSStatusOut(
        slide_id=slide_id,
        tts_status=narr.tts_status,
        audio_url=signed_url_path(narr.audio_key, str(user.id)) if narr.audio_key else None,
        audio_duration_ms=narr.audio_duration_ms,
        tts_error=narr.tts_error,
    )
