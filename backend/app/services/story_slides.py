"""Turn saved story scenes into Naratto slides."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Narration, Project, Slide, StoryScene


def narration_text(narration: str, dialogue: str) -> str:
    spoken = (narration or "").strip()
    line = (dialogue or "").strip()
    if line and line not in spoken:
        return f"{spoken}\n{line}".strip()
    return spoken


def duration_ms(seconds: float) -> int:
    millis = int(round(float(seconds or 0) * 1000))
    return max(1000, millis)


def slide_transition(value: str) -> str:
    if (value or "").strip().lower() in {"none", "cut"}:
        return "none"
    return "fade"


def slide_animation(generation_mode: str) -> str:
    return "wan_i2v" if generation_mode == "video" else "ken_burns"


def motion_prompt(scene: StoryScene) -> str | None:
    if scene.generation_mode != "video":
        return None
    text = (scene.video_prompt or scene.image_prompt or "").strip()
    return text or None


def voice_for_story(project: Project) -> str:
    story = (project.settings or {}).get("story") or {}
    language = str(story.get("language") or "en")
    male = str(story.get("voice") or "female") == "male"
    if language in {"hi", "hinglish"}:
        return "hi-madhur" if male else "hi-swara"
    return "edge-en-andrew" if male else "edge-en-ava"


def replace_project_slides(session: Session, project: Project, scenes: list[StoryScene]) -> int:
    """Replace every slide in the project with one slide per story scene."""
    if not scenes:
        return 0
    slide_ids = list(session.scalars(select(Slide.id).where(Slide.project_id == project.id)).all())
    if slide_ids:
        session.execute(delete(Narration).where(Narration.slide_id.in_(slide_ids)))
        session.execute(delete(Slide).where(Slide.id.in_(slide_ids)))
        session.flush()

    voice = voice_for_story(project)
    ordered = sorted(scenes, key=lambda scene: scene.index)
    for scene in ordered:
        slide_id = uuid.uuid4()
        session.add(
            Slide(
                id=slide_id,
                project_id=project.id,
                order_index=scene.index,
                image_key=None,
                image_keys=[],
                duration_ms=duration_ms(scene.duration),
                transition=slide_transition(scene.transition),
                animation=slide_animation(scene.generation_mode),
                motion_prompt=motion_prompt(scene),
            )
        )
        session.add(
            Narration(
                slide_id=slide_id,
                text=narration_text(scene.narration, scene.dialogue),
                voice=voice,
                speed=1.0,
                tts_status="missing",
            )
        )
    session.flush()
    return len(ordered)
