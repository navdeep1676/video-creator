"""Draw one Qwen-Image-2.1 still per story slide through ComfyUI."""

from __future__ import annotations

import logging
import uuid
import zlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Project, Slide, StoryJob, StoryScene
from app.db.session import SessionLocal
from app.services.aspect_ratios import project_aspect_ratio
from app.services.comfyui import (
    ComfyUIImageProvider,
    build_prompt_graph,
    qwen_canvas,
)
from app.services.openrouter_llm import ProviderUnavailable
from app.services.image_fit import fit_image_to_aspect
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def execute_image_job(job_id: uuid.UUID, provider: ComfyUIImageProvider | None = None) -> None:
    settings = get_settings()
    session = SessionLocal()
    active = provider
    try:
        job = session.get(StoryJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        project = session.get(Project, job.project_id)
        if project is None:
            _fail(job, "Project not found")
            session.commit()
            return
        job.status = "running"
        job.attempts += 1
        session.commit()
        force = bool((job.payload or {}).get("force"))
        active = provider or ComfyUIImageProvider(settings)
        errors = _draw_project(session, project, settings, active, force)
        active.unload()
        if errors:
            _fail(job, "; ".join(errors))
        else:
            job.status = "succeeded"
            job.error = None
        session.commit()
        logger.info("[IMAGE] %s completed", project.id)
    except Exception as exc:
        session.rollback()
        logger.exception("[IMAGE] %s failed", job_id)
        failed = session.get(StoryJob, job_id)
        if failed is not None:
            _fail(failed, str(exc))
            session.commit()
        if active is not None:
            active.unload()
    finally:
        session.close()
        if provider is None and active is not None:
            active.close()


def _draw_project(
    session: Session,
    project: Project,
    settings: Settings,
    provider: ComfyUIImageProvider,
    force: bool,
) -> list[str]:
    slides = list(
        session.scalars(
            select(Slide).where(Slide.project_id == project.id).order_by(Slide.order_index)
        ).all()
    )
    scenes = {
        scene.index: scene
        for scene in session.scalars(
            select(StoryScene).where(StoryScene.project_id == project.id).order_by(StoryScene.index)
        ).all()
    }
    if not slides:
        return ["Create slides from the story before generating images"]
    preset = project_aspect_ratio(project.settings)
    width, height = qwen_canvas(preset.width, preset.height, settings.image_max_side)
    errors: list[str] = []
    drew = False
    skipped_existing = 0
    for slide in slides:
        scene = scenes.get(slide.order_index)
        prompt = (scene.image_prompt if scene is not None else "") or ""
        prompt = prompt.strip()
        if not prompt:
            continue
        if slide.all_image_keys() and not force:
            skipped_existing += 1
            continue
        drew = True
        try:
            graph = build_prompt_graph(
                settings,
                prompt=prompt,
                seed=_seed(slide.id, prompt),
                width=width,
                height=height,
                filename_prefix=f"Naratto/{project.id}/{slide.order_index:03d}",
            )
            raw = provider.generate(graph)
            _store_slide_image(session, project, slide, raw, preset)
            session.commit()
        except ProviderUnavailable:
            raise
        except Exception as exc:
            session.rollback()
            errors.append(f"Slide {slide.order_index + 1}: {exc}")
            logger.exception("[IMAGE] slide %s failed", slide.id)
    if errors or drew or skipped_existing:
        return errors
    return ["No scene has an image prompt"]


def _store_slide_image(session: Session, project: Project, slide: Slide, raw: bytes, preset) -> None:
    storage = get_storage()
    fitted = fit_image_to_aspect(
        raw,
        preset,
        preferred_ext=".png",
        max_long_edge=max(preset.width, preset.height),
    )
    out_ext = fitted.ext if str(fitted.ext).startswith(".") else f".{fitted.ext}"
    if out_ext == ".jpeg":
        out_ext = ".jpg"
    key = f"uploads/{project.id}/images/{uuid.uuid4()}{out_ext}"
    previous = 0
    for old in slide.all_image_keys():
        if storage.exists(old):
            previous += storage.size(old)
            storage.delete(old)
    storage.put_bytes(key, fitted.data)
    project.storage_bytes = max(0, int(project.storage_bytes or 0) - previous + len(fitted.data))
    slide.image_key = key
    slide.image_keys = [{"key": key, "duration_ms": None}]
    session.add(slide)
    session.add(project)


def _seed(slide_id: uuid.UUID, prompt: str) -> int:
    return zlib.crc32(f"{slide_id}:{prompt}".encode("utf-8")) & 0x7FFFFFFF


def _fail(job: StoryJob, message: str) -> None:
    job.status = "failed"
    job.error = message[:2000]
