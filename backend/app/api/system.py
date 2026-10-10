"""Live CPU, RAM, GPU, and running work for the header monitor."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.dependencies import get_current_user
from app.services.activity import system_snapshot

router = APIRouter(tags=["system"])


@router.get("/system")
def system_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return system_snapshot(db, user.id, get_settings())
