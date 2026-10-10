"""Live CPU, RAM, GPU, and running work for the header monitor."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.services.activity import system_snapshot
from app.services.stop_work import StopError, stop_running
from app.utils.exceptions import AppError

router = APIRouter(tags=["system"])


class StopRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)


@router.get("/system")
def system_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return system_snapshot(db, user.id, get_settings())


@router.post("/system/stop")
def stop_system(
    body: StopRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return stop_running(db, user.id, get_settings(), body.id)
    except StopError as exc:
        raise AppError("NOT_RUNNING", str(exc), 404) from exc
