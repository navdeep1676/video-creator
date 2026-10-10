"""Running Naratto jobs for the header monitor, marked GPU or not.

A job is on the GPU only while that work is actually using it. Queued GPU
work stays off the GPU until it starts. Voice, FFmpeg, and cloud story
writing never use the GPU.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Narration, Project, Slide, StoryJob, VideoJob
from app.services.gpu import snapshot
from app.services.host_stats import load_process_roles, sample_host

logger = logging.getLogger(__name__)

_GPU_EXTRA: dict[str, Any] = {"at": 0.0, "payload": {}}
_GPU_EXTRA_TTL_S = 20.0


def story_uses_gpu(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(payload.get("llm_model") or "").startswith("local/")


def render_uses_gpu(stage: str | None) -> bool:
    """Wan sampling uses the GPU. A cached clip and FFmpeg stages do not."""
    text = (stage or "").strip().lower()
    if not text.startswith("wan"):
        return False
    return "cached" not in text


def _running(status: str) -> bool:
    return status in {"running", "processing"}


def _public_status(status: str) -> str:
    return "running" if _running(status) else "queued"


def _item(
    *,
    item_id: str,
    kind: str,
    label: str,
    project_id: str,
    project_title: str,
    status: str,
    progress: int,
    detail: str | None,
    uses_gpu: bool,
    href: str,
) -> dict[str, Any]:
    running = _running(status)
    return {
        "id": item_id,
        "kind": kind,
        "label": label,
        "project_id": project_id,
        "project_title": project_title,
        "status": _public_status(status),
        "progress": max(0, min(100, int(progress or 0))),
        "detail": (detail or "").strip() or None,
        "uses_gpu": uses_gpu,
        "on_gpu": bool(uses_gpu and running),
        "href": href,
    }


def stage_job_item(
    *,
    job_id: str,
    project_id: str,
    project_title: str,
    stage: str,
    status: str,
    progress: int,
    detail: str | None,
    payload: dict | None,
) -> dict[str, Any] | None:
    if stage == "story":
        label = "Story"
        uses_gpu = story_uses_gpu(payload)
    elif stage == "images":
        label = "Scene images"
        uses_gpu = True
    elif stage == "music":
        label = "Music"
        uses_gpu = True
    else:
        return None
    return _item(
        item_id=f"{stage}:{job_id}",
        kind=stage,
        label=label,
        project_id=project_id,
        project_title=project_title,
        status=status,
        progress=progress,
        detail=detail,
        uses_gpu=uses_gpu,
        href=f"/projects/{project_id}",
    )


def video_job_item(
    *,
    job_id: str,
    project_id: str,
    project_title: str,
    status: str,
    progress: int,
    stage: str | None,
) -> dict[str, Any]:
    uses_gpu = render_uses_gpu(stage)
    text = (stage or "").strip()
    if text.lower().startswith("wan"):
        label = "AI motion"
        detail = text
    else:
        label = "Export"
        detail = text or None
    return _item(
        item_id=f"export:{job_id}",
        kind="export",
        label=label,
        project_id=project_id,
        project_title=project_title,
        status=status,
        progress=progress,
        detail=detail,
        uses_gpu=uses_gpu,
        href=f"/projects/{project_id}/export",
    )


def voice_item(project_id: str, project_title: str, counts: dict[str, int]) -> dict[str, Any] | None:
    queued = int(counts.get("queued") or 0)
    processing = int(counts.get("processing") or 0)
    if queued + processing <= 0:
        return None
    total = sum(int(value) for value in counts.values())
    ready = int(counts.get("ready") or 0)
    progress = int(round(100 * ready / total)) if total else 0
    if processing:
        noun = "voice" if processing == 1 else "voices"
        detail = f"{processing} {noun} generating"
        status = "running"
    else:
        noun = "voice" if queued == 1 else "voices"
        detail = f"{queued} {noun} waiting"
        status = "queued"
    return _item(
        item_id=f"voice:{project_id}",
        kind="voice",
        label="Voice",
        project_id=project_id,
        project_title=project_title,
        status=status,
        progress=progress,
        detail=detail,
        uses_gpu=False,
        href=f"/projects/{project_id}",
    )


def list_jobs(session: Session, user_id: UUID) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    stage_rows = session.execute(
        select(StoryJob, Project.title)
        .join(Project, Project.id == StoryJob.project_id)
        .where(
            Project.owner_id == user_id,
            StoryJob.status.in_(("queued", "running")),
        )
        .order_by(StoryJob.created_at.desc())
        .limit(12)
    ).all()
    for job, title in stage_rows:
        item = stage_job_item(
            job_id=str(job.id),
            project_id=str(job.project_id),
            project_title=title or "",
            stage=job.stage,
            status=job.status,
            progress=int(job.progress or 0),
            detail=job.detail,
            payload=job.payload if isinstance(job.payload, dict) else {},
        )
        if item is not None:
            jobs.append(item)

    video_rows = session.execute(
        select(VideoJob, Project.title)
        .join(Project, Project.id == VideoJob.project_id)
        .where(
            VideoJob.user_id == user_id,
            VideoJob.status.in_(("queued", "processing")),
        )
        .order_by(VideoJob.created_at.desc())
        .limit(8)
    ).all()
    for job, title in video_rows:
        jobs.append(
            video_job_item(
                job_id=str(job.id),
                project_id=str(job.project_id),
                project_title=title or "",
                status=job.status,
                progress=int(job.progress or 0),
                stage=job.stage,
            )
        )

    voice_rows = session.execute(
        select(Project.id, Project.title, Narration.tts_status, func.count(Narration.id))
        .join(Slide, Slide.project_id == Project.id)
        .join(Narration, Narration.slide_id == Slide.id)
        .where(Project.owner_id == user_id)
        .group_by(Project.id, Project.title, Narration.tts_status)
    ).all()
    grouped: dict[str, dict[str, Any]] = {}
    for project_id, title, tts_status, count in voice_rows:
        key = str(project_id)
        bucket = grouped.setdefault(key, {"title": title or "", "counts": {}})
        bucket["counts"][str(tts_status)] = int(count)
    for project_id, bucket in grouped.items():
        item = voice_item(project_id, bucket["title"], bucket["counts"])
        if item is not None:
            jobs.append(item)

    jobs.sort(key=lambda row: (0 if row["on_gpu"] else 1 if row["status"] == "running" else 2, row["label"]))
    return jobs


def merge_gpu_totals(host_gpu: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Windows counters own live use. ComfyUI or rocm-smi can still supply the total."""
    used = host_gpu.get("vram_used")
    if used is None:
        used = extra.get("vram_used")
    util = host_gpu.get("utilization")
    if util is None:
        util = extra.get("utilization")
    total = extra.get("vram_total")
    available = any(value is not None for value in (used, util, total)) or bool(host_gpu.get("available"))
    return {
        "available": available,
        "utilization": util,
        "vram_used": used,
        "vram_total": total,
        "temperature": extra.get("temperature"),
    }


def _cached_gpu_extra(settings: Settings) -> dict[str, Any]:
    now = time.monotonic()
    if now - float(_GPU_EXTRA["at"]) < _GPU_EXTRA_TTL_S:
        return dict(_GPU_EXTRA["payload"])
    try:
        payload = snapshot(settings, timeout=0.4)
    except Exception:
        logger.exception("GPU total probe failed")
        payload = {}
    _GPU_EXTRA["at"] = now
    _GPU_EXTRA["payload"] = payload
    return dict(payload)


def system_snapshot(session: Session, user_id: UUID, settings: Settings) -> dict[str, Any]:
    roles = load_process_roles(Path(settings.storage_root) / "run" / "processes.json")
    host = sample_host(roles)
    gpu = merge_gpu_totals(host["gpu"], _cached_gpu_extra(settings))
    try:
        jobs = list_jobs(session, user_id)
    except Exception:
        logger.exception("Running job list failed")
        jobs = []
    return {
        "cpu": host["cpu"],
        "ram": host["ram"],
        "gpu": gpu,
        "jobs": jobs,
        "processes": host["processes"],
    }
