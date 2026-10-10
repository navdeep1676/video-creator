"""Stop buttons for stuck monitor rows. These tests do not kill a process."""

import json
from types import SimpleNamespace
from uuid import uuid4

from app.db.models import Project, StoryJob, VideoJob
from app.services.ace_step import mark_music_failed
from app.services.image_job import _fail
from app.services.stop_work import StopError, parse_stop_id, process_stop_id, stop_running, worker_command_ok
import pytest


def test_known_gpu_programs_can_be_stopped_and_other_processes_cannot():
    assert process_stop_id("ComfyUI") == "process:comfyui"
    assert process_stop_id("ACE-Step") == "process:ace-step"
    assert process_stop_id("Ollama") is None
    assert process_stop_id("Render worker") == "process:render"
    assert process_stop_id("Task worker") == "process:tasks"
    assert process_stop_id("chrome") is None


def test_stop_ids_cover_jobs_and_reject_unknown_rows():
    assert parse_stop_id("images:6f3d1825-6cf7-4953-841b-276b29a77007") == (
        "images",
        "6f3d1825-6cf7-4953-841b-276b29a77007",
    )
    assert parse_stop_id("process:render") == ("process", "render")
    with pytest.raises(StopError):
        parse_stop_id("process:chrome")
    with pytest.raises(StopError):
        parse_stop_id("pid:1234")


def test_worker_stop_requires_the_naratto_celery_command():
    render = "python -m celery -A app.workers.celery_app.celery_app worker -Q render -n render@localhost"
    tasks = "python -m celery -A app.workers.celery_app.celery_app worker -Q tts,default,story-generation"
    assert worker_command_ok(render, "render") is True
    assert worker_command_ok(tasks, "tasks") is True
    assert worker_command_ok(render, "tasks") is False
    assert worker_command_ok(r"C:\Python\python.exe script.py", "render") is False


def test_a_stopped_job_is_not_marked_failed_afterwards():
    image = SimpleNamespace(status="cancelled", error=None)
    music = SimpleNamespace(status="cancelled", error=None)
    _fail(image, "ComfyUI died")
    mark_music_failed(music, RuntimeError("ACE-Step died"))
    assert image.status == "cancelled"
    assert music.status == "cancelled"


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    def get(self, model, key):
        row = self.rows.get(model)
        if row is not None and getattr(row, "id", key) == key:
            return row
        return None

    def add(self, _obj):
        return None

    def commit(self):
        self.committed = True


def test_stopping_scene_images_cancels_the_job_and_stops_comfyui(monkeypatch):
    user_id = uuid4()
    project = SimpleNamespace(id=uuid4(), owner_id=user_id)
    job = SimpleNamespace(
        id=uuid4(),
        stage="images",
        project_id=project.id,
        status="running",
        celery_task_id="task-1",
        error=None,
        detail="Drawing scene 2",
        payload={},
    )
    calls: list[str] = []
    monkeypatch.setattr("app.services.stop_work.revoke_celery_task", lambda *_a, **_k: calls.append("revoke") or True)
    monkeypatch.setattr("app.services.comfyui.stop_comfyui_server", lambda: calls.append("comfy"))
    monkeypatch.setattr("app.services.stop_work._kill_pid", lambda pid: calls.append(f"kill:{pid}") or True)

    result = stop_running(_Session({StoryJob: job, Project: project}), user_id, SimpleNamespace(storage_root="unused"), f"images:{job.id}")

    assert job.status == "cancelled"
    assert job.error == "Stopped by user"
    assert calls == ["revoke", "comfy"]
    assert result["message"].startswith("Stopped scene images")


def test_a_queued_image_job_is_cancelled_without_stopping_comfyui(monkeypatch):
    user_id = uuid4()
    project = SimpleNamespace(id=uuid4(), owner_id=user_id)
    job = SimpleNamespace(
        id=uuid4(),
        stage="images",
        project_id=project.id,
        status="queued",
        celery_task_id="task-2",
        error=None,
        detail=None,
        payload={},
    )
    calls: list[str] = []
    monkeypatch.setattr("app.services.stop_work.revoke_celery_task", lambda *_a, **_k: calls.append("revoke") or True)
    monkeypatch.setattr("app.services.comfyui.stop_comfyui_server", lambda: calls.append("comfy"))

    result = stop_running(_Session({StoryJob: job, Project: project}), user_id, SimpleNamespace(storage_root="unused"), f"images:{job.id}")

    assert job.status == "cancelled"
    assert calls == ["revoke"]
    assert result["message"] == "Stopped scene images"


def test_another_users_job_cannot_be_stopped():
    owner = uuid4()
    project = SimpleNamespace(id=uuid4(), owner_id=owner)
    job = SimpleNamespace(
        id=uuid4(),
        stage="music",
        project_id=project.id,
        status="running",
        celery_task_id=None,
        error=None,
        detail=None,
        payload={},
    )
    with pytest.raises(StopError, match="not running"):
        stop_running(_Session({StoryJob: job, Project: project}), uuid4(), SimpleNamespace(storage_root="unused"), f"music:{job.id}")
    assert job.status == "running"


def test_worker_stop_refuses_a_pid_that_is_not_the_naratto_worker(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "processes.json").write_text(json.dumps({"render": 4242}), encoding="utf-8")
    monkeypatch.setattr("app.services.stop_work._command_line", lambda _pid: r"C:\Windows\System32\notepad.exe")
    killed: list[int] = []
    monkeypatch.setattr("app.services.stop_work._kill_pid", lambda pid: killed.append(pid) or True)

    with pytest.raises(StopError, match="not the render worker"):
        stop_running(None, uuid4(), SimpleNamespace(storage_root=str(tmp_path)), "process:render")
    assert killed == []


def test_worker_stop_kills_only_the_matching_celery_worker(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "processes.json").write_text(json.dumps({"tasks": 77}), encoding="utf-8")
    monkeypatch.setattr(
        "app.services.stop_work._command_line",
        lambda _pid: "python -m celery -A app.workers.celery_app.celery_app worker -Q story-generation",
    )
    killed: list[int] = []
    monkeypatch.setattr("app.services.stop_work._kill_pid", lambda pid: killed.append(pid) or True)

    result = stop_running(None, uuid4(), SimpleNamespace(storage_root=str(tmp_path)), "process:tasks")

    assert killed == [77]
    assert "naratto restart" in result["message"]


def test_a_processing_export_also_stops_the_render_worker(tmp_path, monkeypatch):
    user_id = uuid4()
    job = SimpleNamespace(id=uuid4(), user_id=user_id, status="processing")
    run = tmp_path / "run"
    run.mkdir()
    (run / "processes.json").write_text(json.dumps({"render": 55}), encoding="utf-8")
    monkeypatch.setattr("app.services.stop_work.cancel_video_job", lambda _session, row: row)
    monkeypatch.setattr(
        "app.services.stop_work._command_line",
        lambda _pid: "python -m celery -A app.workers.celery_app.celery_app worker -Q render -n render@localhost",
    )
    killed: list[int] = []
    monkeypatch.setattr("app.services.stop_work._kill_pid", lambda pid: killed.append(pid) or True)

    result = stop_running(_Session({VideoJob: job}), user_id, SimpleNamespace(storage_root=str(tmp_path)), f"export:{job.id}")

    assert killed == [55]
    assert "naratto restart" in result["message"]


def test_a_queued_export_does_not_kill_the_render_worker(monkeypatch):
    user_id = uuid4()
    job = SimpleNamespace(id=uuid4(), user_id=user_id, status="queued")
    monkeypatch.setattr("app.services.stop_work.cancel_video_job", lambda _session, row: row)
    killed: list[int] = []
    monkeypatch.setattr("app.services.stop_work._kill_pid", lambda pid: killed.append(pid) or True)

    result = stop_running(_Session({VideoJob: job}), user_id, SimpleNamespace(storage_root="unused"), f"export:{job.id}")

    assert killed == []
    assert result["message"] == "Stopped the export"
