from __future__ import annotations

from uuid import UUID

from fastapi import Cookie, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.services.storage import LocalStorage, get_storage
from app.utils.exceptions import AppError
from app.utils.security import safe_decode

bearer_scheme = HTTPBearer(auto_error=False)


def get_storage_dep() -> LocalStorage:
    return get_storage()


def get_current_user(
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(default=None),
) -> User:
    token = None
    if creds:
        token = creds.credentials
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise AppError("UNAUTHORIZED", "Missing access token", 401)
    payload = safe_decode(token)
    if not payload or payload.get("type") != "access":
        raise AppError("UNAUTHORIZED", "Invalid or expired access token", 401)
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise AppError("UNAUTHORIZED", "Invalid token subject", 401)
    user = db.get(User, user_id)
    if not user:
        raise AppError("UNAUTHORIZED", "User not found", 401)
    return user


def get_refresh_token(refresh_token: str | None = Cookie(default=None, alias="refresh_token")) -> str | None:
    return refresh_token
