from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.projects import get_owned_project
from app.config import get_settings
from app.db.models import MusicAsset, User
from app.db.session import get_db
from app.dependencies import get_current_user, get_storage_dep
from app.schemas.common import MusicAssetOut
from app.services.storage import LocalStorage
from app.utils.exceptions import AppError
from app.utils.files import validate_audio_bytes

router = APIRouter(tags=["music"])


@router.get("/projects/{project_id}/music", response_model=list[MusicAssetOut])
def list_music(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MusicAsset]:
    project = get_owned_project(db, project_id, user)
    return list(db.scalars(select(MusicAsset).where(MusicAsset.project_id == project.id)).all())


@router.post("/projects/{project_id}/music", response_model=MusicAssetOut)
async def upload_music(
    project_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage_dep),
) -> MusicAsset:
    settings = get_settings()
    if not settings.feature_bgm:
        raise AppError("FEATURE_DISABLED", "Background music is disabled", 400)
    project = get_owned_project(db, project_id, user)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", "Music file exceeds 20MB", 413)
    try:
        ext = validate_audio_bytes(data, file.filename or "track.mp3")
    except ValueError as e:
        raise AppError("INVALID_AUDIO", str(e), 400) from e
    asset_id = uuid4()
    key = f"uploads/{project.id}/music/{asset_id}{ext}"
    storage.put_bytes(key, data)
    project.storage_bytes += len(data)
    asset = MusicAsset(
        id=asset_id,
        project_id=project.id,
        storage_key=key,
        filename=file.filename or f"{asset_id}{ext}",
        size_bytes=len(data),
    )
    db.add(asset)
    db.add(project)
    db.commit()
    db.refresh(asset)
    return asset
