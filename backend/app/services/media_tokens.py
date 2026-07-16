from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote, unquote

from app.config import get_settings


def _normalize_key(object_key: str) -> str:
    """Normalize storage key for stable signing (no leading slash, decoded)."""
    key = unquote(object_key or "").lstrip("/").replace("\\", "/")
    return key


def sign_media_key(object_key: str, user_id: str | None = None) -> dict[str, str | int]:
    """
    Sign a media object key for short-lived GET access.

    Note: user_id is intentionally NOT part of the HMAC. Media is loaded via
    <img>/<audio>/<video> which cannot send Authorization headers, so verify
    must only use key + exp + sig (plus server secret).
    """
    del user_id  # accepted for call-site compatibility; not used in payload
    settings = get_settings()
    key = _normalize_key(object_key)
    exp = int(time.time()) + settings.media_token_ttl_seconds
    # Payload: object_key|exp only
    payload = f"{key}|{exp}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"object_key": key, "exp": exp, "sig": sig}


def verify_media_signature(object_key: str, exp: int, sig: str, user_id: str | None = None) -> bool:
    del user_id
    settings = get_settings()
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False
    key = _normalize_key(object_key)
    payload = f"{key}|{exp_i}"
    expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not sig or not isinstance(sig, str):
        return False
    return hmac.compare_digest(expected, sig)


def signed_url_path(object_key: str, user_id: str | None = None) -> str:
    """Return relative API path with query params for media GET."""
    token = sign_media_key(object_key, user_id)
    key_path = quote(str(token["object_key"]), safe="/")
    return f"/api/v1/files/{key_path}?exp={token['exp']}&sig={token['sig']}"
