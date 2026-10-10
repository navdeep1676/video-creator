"""Draw one Qwen-Image-2.1 still per story slide through ComfyUI."""

from __future__ import annotations

import inspect
import logging
import uuid
import zlib
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Project, Slide, StoryJob, StoryScene
from app.db.session import SessionLocal
from app.services.aspect_ratios import project_aspect_ratio
from app.services.comfyui import (
    ComfyUIImageProvider,
    ImageGenerationError,
    build_prompt_graph,
    ensure_comfyui_server,
    qwen_canvas,
    should_manage_comfyui,
    stop_comfyui_server,
)
from app.services.openrouter_llm import ProviderUnavailable
from app.services.image_fit import fit_image_to_aspect
from app.services.stage_job import begin_stage_job, report_progress
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

# Qwen sees this with the previous still, then the scene prompt.
_REFERENCE_LINE = (
    "Keep the same characters, faces, clothing, colors, and art style as the reference image. "
)


def execute_image_job(
    job_id: uuid.UUID,
    provider: ComfyUIImageProvider | None = None,
    task_id: str | None = None,
) -> None:
    settings = get_settings()
    session = SessionLocal()
    active = provider
    try:
        job = begin_stage_job(session, job_id, task_id)
        if job is None:
            return
        project = session.get(Project, job.project_id)
        if project is None:
            _fail(job, "Project not found")
            session.commit()
            return
        force = bool((job.payload or {}).get("force"))
        active = provider or ComfyUIImageProvider(settings)
        manage_gpu = should_manage_comfyui(settings, injected_provider=provider is not None)

        def on_progress(percent: int, detail: str) -> None:
            report_progress(session, job, percent, detail)

        def on_start() -> None:
            if not manage_gpu:
                return
            report_progress(session, job, 0, "Starting ComfyUI")
            ensure_comfyui_server(settings)

        errors = _draw_project(
            session,
            project,
            settings,
            active,
            force,
            on_progress=on_progress,
            on_start=on_start if manage_gpu else None,
        )
        active.unload()
        if errors:
            _fail(job, "; ".join(errors))
        else:
            job.status = "succeeded"
            job.progress = 100
            job.detail = "Scene images are ready"
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
        if "manage_gpu" in locals() and manage_gpu:
            try:
                stop_comfyui_server()
            except Exception:
                logger.exception("[IMAGE] ComfyUI did not stop")
        session.close()
        if provider is None and active is not None:
            active.close()


def _draw_project(
    session: Session,
    project: Project,
    settings: Settings,
    provider: ComfyUIImageProvider,
    force: bool,
    on_progress: Callable[[int, str], None] | None = None,
    on_start: Callable[[], None] | None = None,
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
    pending: list[tuple[Slide, str]] = []
    for slide in slides:
        scene = scenes.get(slide.order_index)
        prompt = (scene.image_prompt if scene is not None else "") or ""
        prompt = prompt.strip()
        if not prompt:
            continue
        if slide.all_image_keys() and not force:
            skipped_existing += 1
            continue
        pending.append((slide, prompt))
    total = len(pending)
    if pending and on_start is not None:
        on_start()
    if pending:
        ensure = getattr(provider, "ensure_nodes", None)
        if callable(ensure):
            try:
                ensure()
            except ProviderUnavailable:
                raise
            except ImageGenerationError as exc:
                return [str(exc)]
    published = {"percent": -1, "detail": ""}
    storage = get_storage()
    previous: bytes | None = None
    pending_at = 0

    def publish(percent: int, detail: str) -> None:
        if on_progress is None:
            return
        percent = max(0, min(99, int(percent)))
        if percent == published["percent"] and detail == published["detail"]:
            return
        published["percent"] = percent
        published["detail"] = detail
        on_progress(percent, detail)

    for slide in slides:
        if pending_at >= len(pending) or pending[pending_at][0] is not slide:
            kept = _read_slide_image(storage, slide)
            if kept:
                previous = kept
            continue
        index = pending_at
        pending_at += 1
        prompt = pending[index][1]
        drew = True
        base = int(100 * index / total) if total else 0
        cap = int(100 * (index + 1) / total) if total else 99
        order = slide.order_index + 1
        reference_name = _upload_reference(provider, previous, slide.order_index)
        using = " from the previous image" if reference_name else ""
        publish(base, f"Drawing scene {order}{using} · image {index + 1} of {total}")

        def on_step(
            value: int,
            maximum: int,
            base=base,
            cap=cap,
            order=order,
            index=index,
            total=total,
            using=using,
        ) -> None:
            frac = 0.0 if maximum <= 0 else min(1.0, value / maximum)
            publish(
                int(base + (cap - base) * frac),
                f"Drawing scene {order}{using} · step {value} of {maximum} · image {index + 1} of {total}",
            )

        try:
            scene_prompt = f"{_REFERENCE_LINE}{prompt}" if reference_name else prompt
            graph = build_prompt_graph(
                settings,
                prompt=scene_prompt,
                seed=_seed(slide.id, prompt),
                width=width,
                height=height,
                filename_prefix=f"Naratto/{project.id}/{slide.order_index:03d}",
                reference_image=reference_name,
            )
            raw = _call_generate(provider, graph, on_step)
            _store_slide_image(session, project, slide, raw, preset)
            session.commit()
            previous = raw
            publish(cap, f"Saved scene {order} · {index + 1} of {total}")
        except ProviderUnavailable:
            raise
        except Exception as exc:
            session.rollback()
            errors.append(f"Slide {order}: {exc}")
            logger.exception("[IMAGE] slide %s failed", slide.id)
            kept = _read_slide_image(storage, slide)
            if kept:
                previous = kept
    if errors or drew or skipped_existing:
        return errors
    return ["No scene has an image prompt"]


def _read_slide_image(storage, slide: Slide) -> bytes | None:
    keys = slide.all_image_keys()
    if not keys or not storage.exists(keys[0]):
        return None
    return storage.get_bytes(keys[0])


def _upload_reference(provider, previous: bytes | None, order_index: int) -> str | None:
    if not previous:
        return None
    upload = getattr(provider, "upload_image", None)
    if not callable(upload):
        return None
    suffix = "jpg" if previous.startswith(b"\xff\xd8") else "png"
    return upload(previous, f"naratto-ref-{order_index:03d}.{suffix}")


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


def _call_generate(provider: ComfyUIImageProvider, graph: dict, on_step: Callable[[int, int], None]):
    method = provider.generate
    try:
        accepts = "on_step" in inspect.signature(method).parameters
    except (TypeError, ValueError):
        accepts = False
    if accepts:
        return method(graph, on_step=on_step)
    return method(graph)


def _seed(slide_id: uuid.UUID, prompt: str) -> int:
    return zlib.crc32(f"{slide_id}:{prompt}".encode("utf-8")) & 0x7FFFFFFF


def _fail(job: StoryJob, message: str) -> None:
    job.status = "failed"
    job.error = message[:2000]
