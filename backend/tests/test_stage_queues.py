"""Story and music run on Celery queues, and a crashed in-process job can be reclaimed."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.services.stage_job import claim_action, is_abandoned_inline_job
from app.workers.celery_app import celery_app
from app.workers.tasks import generate_music, generate_story


def test_claim_action_starts_once_and_resumes_the_same_delivery():
    assert claim_action("queued", None, "task-1") == "claim"
    assert claim_action("running", "task-1", "task-1") == "resume"
    assert claim_action("running", None, "task-1") == "resume"
    assert claim_action("running", "task-1", "task-2") == "skip"
    assert claim_action("succeeded", "task-1", "task-1") == "skip"
    assert claim_action("failed", None, "task-1") == "skip"


def test_abandoned_inline_story_jobs_are_old_and_have_no_celery_id():
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=5)
    fresh = now - timedelta(seconds=5)
    assert is_abandoned_inline_job(
        stage="story", status="running", celery_task_id=None, created_at=old, now=now
    )
    assert is_abandoned_inline_job(
        stage="music", status="queued", celery_task_id=None, created_at=old, now=now
    )
    assert not is_abandoned_inline_job(
        stage="story", status="running", celery_task_id="task-1", created_at=old, now=now
    )
    assert not is_abandoned_inline_job(
        stage="story", status="running", celery_task_id=None, created_at=fresh, now=now
    )
    assert not is_abandoned_inline_job(
        stage="images", status="running", celery_task_id=None, created_at=old, now=now
    )


def test_stage_tasks_use_separate_queues():
    routes = celery_app.conf.task_routes
    assert routes["app.workers.tasks.generate_story"]["queue"] == "story-generation"
    assert routes["app.workers.tasks.generate_music"]["queue"] == "music-generation"
    assert routes["app.workers.tasks.generate_project_images"]["queue"] == "image-generation"
    assert routes["app.workers.tasks.generate_slide_tts"]["queue"] == "tts"
    assert routes["app.workers.tasks.render_video"]["queue"] == "render"
    assert routes["app.workers.tasks.reclaim_stuck_jobs"]["queue"] == "default"


def test_story_and_music_tasks_forward_only_the_job_id(monkeypatch):
    job_id = "11111111-1111-1111-1111-111111111111"
    seen: list[dict] = []

    def fake_story(job, provider=None, task_id=None):
        seen.append({"kind": "story", "job": job, "provider": provider, "task_id": task_id})

    def fake_music(job, provider=None, task_id=None):
        seen.append({"kind": "music", "job": job, "provider": provider, "task_id": task_id})

    monkeypatch.setattr("app.services.story_job.execute_story_job", fake_story)
    monkeypatch.setattr("app.services.music_job.execute_music_job", fake_music)
    generate_story.push_request(id="story-task")
    generate_music.push_request(id="music-task")
    try:
        generate_story.run(job_id)
        generate_music.run(job_id)
    finally:
        generate_story.pop_request()
        generate_music.pop_request()
    assert seen == [
        {"kind": "story", "job": UUID(job_id), "provider": None, "task_id": "story-task"},
        {"kind": "music", "job": UUID(job_id), "provider": None, "task_id": "music-task"},
    ]
