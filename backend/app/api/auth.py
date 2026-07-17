from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.dependencies import get_current_user, get_refresh_token
from app.schemas.common import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)
from app.utils.exceptions import AppError
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        secure=settings.use_secure_cookies,
        samesite="lax",
    )


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise AppError("EMAIL_TAKEN", "Email already registered", 409)
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(access_token=access, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)
    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(access_token=access, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Depends(get_refresh_token),
) -> TokenResponse:
    if not refresh_token:
        raise AppError("UNAUTHORIZED", "Missing refresh token", 401)
    payload = safe_decode(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AppError("UNAUTHORIZED", "Invalid refresh token", 401)
    from uuid import UUID

    user = db.get(User, UUID(payload["sub"]))
    if not user:
        raise AppError("UNAUTHORIZED", "User not found", 401)
    access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=access, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(response: Response) -> dict:
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update display name and/or email for the current user."""
    if body.display_name is None and body.email is None:
        raise AppError("VALIDATION", "Provide display_name and/or email to update", 400)

    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise AppError("VALIDATION", "Display name cannot be empty", 400)
        user.display_name = name

    if body.email is not None:
        new_email = str(body.email).lower().strip()
        if new_email != user.email:
            taken = db.scalar(select(User).where(User.email == new_email, User.id != user.id))
            if taken:
                raise AppError("EMAIL_TAKEN", "Email already registered", 409)
            user.email = new_email

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Current password is incorrect", 400)
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.commit()
    return {"ok": True}
