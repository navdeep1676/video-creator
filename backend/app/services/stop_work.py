"""Stop one stuck monitor row.

Jobs are marked cancelled and their Celery task is revoked. A GPU program
that is holding the card (ComfyUI, ACE-Step, or the render worker)
is stopped too, because a solo worker blocked inside that program will not
notice the cancel by itself.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Narration, Project, Slide, StoryJob, VideoJob
from app.services.job_control import cancel_project_tts, cancel_video_job, revoke_celery_task

logger = logging.getLogger(__name__)

PROCESS_STOP_IDS = {
    "ComfyUI": "process:comfyui",
    "ACE-Step": "process:ace-step",
    "Render worker": "process:render",
    "Task worker": "process:tasks",
}

_JOB_KINDS = {"story", "images", "music", "export", "voice"}
_PROCESS_KINDS = {"comfyui", "ace-step", "render", "tasks"}


class StopError(ValueError):
    """The row cannot be stopped."""


def process_stop_id(name: str) -> str | None:
    return PROCESS_STOP_IDS.get(name)


def parse_stop_id(stop_id: str) -> tuple[str, str]:
    kind, sep, rest = (stop_id or "").strip().partition(":")
    if not sep or not rest:
        raise StopError("Unknown process")
    if kind in _JOB_KINDS:
        return kind, rest
    if kind == "process" and rest in _PROCESS_KINDS:
        return kind, rest
    raise StopError("Unknown process")


def worker_command_ok(command: str, kind: str) -> bool:
    """True when this command line is the Naratto worker we mean to stop."""
    text = (command or "").lower()
    if "celery" not in text or "app.workers.celery_app" not in text:
        return False
    if kind == "render":
        return "-q render" in text or "render@localhost" in text
    if kind == "tasks":
        return "story-generation" in text
    return False


def stop_running(session: Session, user_id: UUID, settings: Settings, stop_id: str) -> dict:
    kind, rest = parse_stop_id(stop_id)
    if kind == "process":
        message = _stop_process(settings, rest)
        return {"stopped": True, "message": message}
    if kind == "voice":
        return _stop_voice(session, user_id, rest)
    if kind == "export":
        return _stop_export(session, user_id, settings, rest)
    return _stop_stage(session, user_id, settings, kind, rest)


def _stop_voice(session: Session, user_id: UUID, project_id: str) -> dict:
    project = _owned_project(session, user_id, project_id)
    if not _narration_busy(session, project.id):
        raise StopError("Voice is not running")
    cancel_project_tts(session, project)
    return {"stopped": True, "message": "Stopped voice generation"}


def _stop_export(session: Session, user_id: UUID, settings: Settings, job_id: str) -> dict:
    job = session.get(VideoJob, _uuid(job_id))
    if job is None or job.user_id != user_id:
        raise StopError("Export is not running")
    running = job.status == "processing"
    if job.status not in {"queued", "processing"}:
        raise StopError("Export is not running")
    cancel_video_job(session, job)
    message = "Stopped the export"
    if running:
        note = _stop_worker(settings, "render")
        message = f"Stopped the export. {note}"
    return {"stopped": True, "message": message}


def _stop_stage(session: Session, user_id: UUID, settings: Settings, stage: str, job_id: str) -> dict:
    job = session.get(StoryJob, _uuid(job_id))
    if job is None or job.stage != stage:
        raise StopError("That job is not running")
    project = session.get(Project, job.project_id)
    if project is None or project.owner_id != user_id:
        raise StopError("That job is not running")
    if job.status not in {"queued", "running"}:
        raise StopError("That job is not running")
    running = job.status == "running"
    task_id = job.celery_task_id
    job.status = "cancelled"
    job.error = "Stopped by user"
    job.detail = "Stopped"
    session.add(job)
    session.commit()
    revoke_celery_task(task_id, terminate=True)
    extra = _release_stage_gpu(settings, job, running)
    label = {"story": "story", "images": "scene images", "music": "music"}.get(stage, stage)
    message = f"Stopped {label}"
    if extra:
        message = f"{message}. {extra}"
    return {"stopped": True, "message": message}


def _release_stage_gpu(_settings: Settings, job: StoryJob, running: bool) -> str:
    if not running:
        return ""
    if job.stage == "images":
        from app.services.comfyui import stop_comfyui_server

        stop_comfyui_server()
        return "ComfyUI was stopped so the GPU is free"
    if job.stage == "music":
        from app.services.ace_step import stop_acestep_server

        stop_acestep_server()
        return "ACE-Step was stopped so the GPU is free"
    return ""


def _stop_process(settings: Settings, kind: str) -> str:
    if kind == "comfyui":
        from app.services.comfyui import stop_comfyui_server

        stop_comfyui_server()
        return "Stopped ComfyUI"
    if kind == "ace-step":
        from app.services.ace_step import stop_acestep_server

        stop_acestep_server()
        return "Stopped ACE-Step"
    if kind in {"render", "tasks"}:
        return _stop_worker(settings, kind)
    raise StopError("Unknown process")


def _stop_worker(settings: Settings, kind: str) -> str:
    pid = _recorded_pid(settings, kind)
    if pid <= 0:
        raise StopError(f"The {kind} worker is not recorded. Start the stack again with naratto.")
    command = _command_line(pid)
    if not worker_command_ok(command, kind):
        raise StopError(f"Refused to stop pid {pid}. It is not the {kind} worker.")
    if not _kill_pid(pid):
        raise StopError(f"Could not stop the {kind} worker")
    name = "render worker" if kind == "render" else "task worker"
    return f"Stopped the {name}. Run naratto restart before the next job."


def _recorded_pid(settings: Settings, kind: str) -> int:
    path = Path(settings.storage_root) / "run" / "processes.json"
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return int(payload.get(kind) or 0)
    except (OSError, ValueError, TypeError):
        return 0


def _command_line(pid: int) -> str:
    if os.name != "nt" or pid <= 0:
        return ""
    script = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
    try:
        listed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return listed.stdout or ""


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(int(pid))],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    try:
        os.kill(pid, 15)
    except OSError:
        return False
    return True


def _owned_project(session: Session, user_id: UUID, project_id: str) -> Project:
    project = session.get(Project, _uuid(project_id))
    if project is None or project.owner_id != user_id:
        raise StopError("Voice is not running")
    return project


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise StopError("Unknown process") from exc


def _narration_busy(session: Session, project_id: UUID) -> bool:
    rows = session.scalars(
        select(Narration)
        .join(Slide, Slide.id == Narration.slide_id)
        .where(Slide.project_id == project_id, Narration.tts_status.in_(("queued", "processing")))
    ).all()
    return bool(rows)
