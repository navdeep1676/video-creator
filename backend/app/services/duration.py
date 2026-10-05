from __future__ import annotations

from app.config import get_settings
from app.db.models import Narration, Slide


def effective_duration_ms(slide: Slide, narration: Narration | None = None) -> int:
    """Picture length. Speech can extend a scene. It does not shrink a longer scene."""
    settings = get_settings()
    narr = narration if narration is not None else slide.narration
    spoken = _spoken_ms(narr)
    slide_ms = int(slide.duration_ms or 0)
    if spoken and slide_ms:
        return max(spoken, slide_ms)
    if spoken:
        return spoken
    if slide_ms > 0:
        return slide_ms
    return settings.default_duration_ms


def scene_timeline_ms(planned_ms: int, slide_ms: int, spoken_ms: int) -> int:
    """Restore a planned scene when TTS copied the spoken length onto the slide."""
    planned = max(0, int(planned_ms or 0))
    slide = max(0, int(slide_ms or 0))
    spoken = max(0, int(spoken_ms or 0))
    if spoken and slide == spoken and planned > slide:
        return planned
    if spoken or slide:
        return max(slide, spoken)
    return planned


def _spoken_ms(narr: Narration | None) -> int:
    if narr and narr.tts_status == "ready" and narr.audio_duration_ms:
        return int(narr.audio_duration_ms)
    return 0
