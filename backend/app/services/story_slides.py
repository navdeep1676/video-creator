"""Turn saved story scenes into Naratto slides."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Narration, Project, Slide, StoryScene
from app.services.duration import scene_timeline_ms


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
    # Video scenes animate the still with Wan2.2 TI2V 5B.
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


def align_story_slide_durations(session: Session, project_id: uuid.UUID) -> int:
    """Put planned scene lengths back when speech was copied onto the slide."""
    scenes = list(
        session.scalars(
            select(StoryScene).where(StoryScene.project_id == project_id).order_by(StoryScene.index)
        ).all()
    )
    if not scenes:
        return 0
    slides = list(
        session.scalars(
            select(Slide)
            .options(selectinload(Slide.narration))
            .where(Slide.project_id == project_id)
            .order_by(Slide.order_index)
        ).all()
    )
    by_index = {scene.index: scene for scene in scenes}
    changed = 0
    for slide in slides:
        scene = by_index.get(slide.order_index)
        if scene is None:
            continue
        spoken = 0
        narr = slide.narration
        if narr and narr.tts_status == "ready" and narr.audio_duration_ms:
            spoken = int(narr.audio_duration_ms)
        target = scene_timeline_ms(duration_ms(scene.duration), int(slide.duration_ms or 0), spoken)
        if target and target != int(slide.duration_ms or 0):
            slide.duration_ms = target
            session.add(slide)
            changed += 1
    return changed


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
