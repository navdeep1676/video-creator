from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "video_creator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": settings.visibility_timeout_s},
    task_routes={
        "app.workers.tasks.generate_slide_tts": {"queue": "tts"},
        "app.workers.tasks.render_video": {"queue": "render"},
        "app.workers.tasks.reclaim_stuck_jobs": {"queue": "default"},
    },
    task_default_queue="default",
    beat_schedule={
        "reclaim-stuck-jobs": {
            "task": "app.workers.tasks.reclaim_stuck_jobs",
            "schedule": 60.0,
        },
    },
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
)
