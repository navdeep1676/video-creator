"""Run one story-planning job and store the plan on a Naratto project."""

from __future__ import annotations

import logging
import uuid
import zlib
from types import SimpleNamespace

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Project, Story, StoryCharacter, StoryJob, StoryLocation, StoryScene
from app.db.session import SessionLocal
from app.services.gemini_llm import GeminiLLMProvider, is_gemini_model
from app.services.local_llm import LocalLLMProvider, is_local_model
from app.services.openai_llm import OpenAILLMProvider, is_openai_model
from app.services.openrouter_llm import LLMProvider, OpenRouterLLMProvider
from app.services.story_planner import StoryPlan, plan_story, plan_to_json
from app.services.story_slides import replace_project_slides
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def build_llm_provider(settings: Settings, model: str, override: LLMProvider | None = None) -> LLMProvider:
    if override is not None:
        return override
    if is_local_model(model):
        tuned = settings.model_copy(update={"local_llm_model": model})
        return LocalLLMProvider(tuned)
    if is_gemini_model(model):
        tuned = settings.model_copy(update={"gemini_model": model})
        return GeminiLLMProvider(tuned)
    if is_openai_model(model):
        tuned = settings.model_copy(update={"openai_model": model})
        return OpenAILLMProvider(tuned)
    tuned = settings.model_copy(update={"openrouter_model": model})
    return OpenRouterLLMProvider(tuned)


def execute_story_job(job_id: uuid.UUID, provider: LLMProvider | None = None) -> None:
    settings = get_settings()
    session = SessionLocal()
    try:
        job = session.get(StoryJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        project = session.get(Project, job.project_id)
        if project is None:
            job.status = "failed"
            job.error = "Project not found"
            session.commit()
            return
        job.status = "running"
        job.attempts += 1
        session.commit()
        active = provider or build_llm_provider(settings, str(job.payload.get("llm_model") or settings.openrouter_model))
        plan = plan_story(SimpleNamespace(**job.payload), active, settings)
        save_story(session, project, plan)
        job.status = "succeeded"
        job.error = None
        session.commit()
        logger.info("[STORY] %s completed", project.id)
    except Exception as exc:
        session.rollback()
        logger.exception("[STORY] %s failed", job_id)
        failed = session.get(StoryJob, job_id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)
            session.commit()
    finally:
        session.close()


def save_story(session: Session, project: Project, plan: StoryPlan) -> None:
    session.execute(delete(StoryScene).where(StoryScene.project_id == project.id))
    session.flush()
    session.execute(delete(StoryCharacter).where(StoryCharacter.project_id == project.id))
    session.execute(delete(StoryLocation).where(StoryLocation.project_id == project.id))
    session.execute(delete(Story).where(Story.project_id == project.id))
    session.flush()

    character_ids: dict[str, uuid.UUID] = {}
    for draft in plan.characters:
        row = StoryCharacter(
            project_id=project.id,
            name=draft.name[:256],
            age=(draft.age or "")[:32] or None,
            appearance=draft.appearance,
            clothing=draft.clothing,
            personality=draft.personality,
            style=draft.visual_style,
            seed=zlib.crc32(draft.name.strip().lower().encode("utf-8")) & 0x7FFFFFFF,
        )
        session.add(row)
        session.flush()
        character_ids[draft.name] = row.id

    location_ids: dict[str, uuid.UUID] = {}
    for draft in plan.locations:
        row = StoryLocation(
            project_id=project.id,
            name=draft.name[:256],
            description=draft.description,
            lighting=draft.lighting,
            mood=draft.mood,
        )
        session.add(row)
        session.flush()
        location_ids[draft.name] = row.id

    for index, draft in enumerate(plan.scenes):
        session.add(
            StoryScene(
                project_id=project.id,
                index=index,
                beat=draft.beat[:32],
                start_time=draft.start_time,
                end_time=draft.end_time,
                duration=draft.duration,
                narration=draft.narration,
                dialogue=draft.dialogue,
                character_ids=[str(character_ids[name]) for name in draft.character_names if name in character_ids],
                location_id=location_ids.get(draft.location_name),
                image_prompt=draft.image_prompt,
                video_prompt=draft.video_prompt,
                camera_motion=draft.camera_motion[:32],
                transition=draft.transition[:32],
                sfx=draft.sfx,
                generation_mode=draft.generation_mode,
                status="pending",
            )
        )

    session.add(
        Story(
            project_id=project.id,
            title=plan.title,
            hook=plan.hook,
            body=plan.story,
            lyrics=plan.lyrics,
            plan=plan.model_dump(),
        )
    )
    storage = get_storage()
    prefix = f"projects/{project.id}/story"
    storage.put_bytes(f"{prefix}/story.json", plan_to_json(plan).encode("utf-8"))
    narration = "\n".join(scene.narration.strip() for scene in plan.scenes)
    storage.put_bytes(f"{prefix}/narration.txt", (narration + "\n").encode("utf-8"))
    session.flush()
    scene_rows = list(
        session.scalars(
            select(StoryScene).where(StoryScene.project_id == project.id).order_by(StoryScene.index)
        ).all()
    )
    replace_project_slides(session, project, scene_rows)


def latest_story_job(session: Session, project_id: uuid.UUID) -> StoryJob | None:
    return session.scalar(
        select(StoryJob)
        .where(StoryJob.project_id == project_id, StoryJob.stage == "story")
        .order_by(StoryJob.created_at.desc())
        .limit(1)
    )
