from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, Response

from app.services.media_tokens import verify_media_signature
from app.services.storage import get_storage
from app.utils.exceptions import AppError

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{object_key:path}")
def get_file(
    object_key: str,
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    if not verify_media_signature(object_key, exp, sig):
        raise AppError("FORBIDDEN", "Invalid or expired media signature", 403)
    storage = get_storage()
    if not storage.exists(object_key):
        raise AppError("NOT_FOUND", "File not found", 404)
    path: Path = storage.absolute_path(object_key)
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path,
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )
