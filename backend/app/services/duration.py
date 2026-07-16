from __future__ import annotations

from app.config import get_settings
from app.db.models import Narration, Slide


def effective_duration_ms(slide: Slide, narration: Narration | None = None) -> int:
    settings = get_settings()
    narr = narration if narration is not None else slide.narration
    if narr and narr.tts_status == "ready" and narr.audio_duration_ms:
        return int(narr.audio_duration_ms)
    if slide.duration_ms and slide.duration_ms > 0:
        return int(slide.duration_ms)
    return settings.default_duration_ms
