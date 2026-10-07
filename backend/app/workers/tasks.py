from __future__ import annotations

import shutil
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import MusicAsset, Narration, Project, Slide, VideoJob
from app.db.session import SessionLocal
from app.services.aspect_ratios import DEFAULT_ASPECT_RATIO, canvas_for_quality, resolve_aspect_ratio
from app.services.duration import effective_duration_ms
from app.services.export_readiness import slides_for_render
from app.services.ffmpeg_pipeline import RenderOptions, SlideMedia, render_project_video
from app.services.music_job import music_storage_key
from app.services.story_slides import align_story_slide_durations
from app.services.storage import get_storage
from app.services.subtitles import load_cues
from app.services.tts_service import synthesize_to_mp3
from app.utils.exceptions import NonRetryableTaskError, RetryableTaskError
from app.workers.celery_app import celery_app


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.generate_slide_tts",
    max_retries=2,
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def generate_slide_tts(self, slide_id: str, force: bool = False) -> dict:
    db = SessionLocal()
    storage = get_storage()
    try:
        slide = db.scalar(
            select(Slide).options(selectinload(Slide.narration), selectinload(Slide.project)).where(Slide.id == UUID(slide_id))
        )
        if not slide or not slide.narration:
            raise NonRetryableTaskError("NOT_FOUND", "Slide/narration not found")
        narr = slide.narration
        if narr.tts_status == "cancelled":
            return {"status": "cancelled", "slide_id": slide_id}
        if narr.tts_status == "ready" and narr.audio_key and not force:
            return {"status": "ready", "slide_id": slide_id}

        narr.tts_status = "processing"
        narr.tts_error = None
        narr.celery_task_id = self.request.id
        db.add(narr)
        db.commit()

        text = (narr.text or "").strip()
        if not text:
            raise NonRetryableTaskError("VALIDATION", "Empty narration text")

        audio_key = f"uploads/{slide.project_id}/audio/{slide.id}.mp3"
        abs_path = storage.absolute_path(audio_key)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            duration_ms = synthesize_to_mp3(text, abs_path, narr.voice, narr.speed)
        except Exception as e:
            # User cancel / worker terminate often surfaces as connection errors
            db.refresh(narr)
            if narr.tts_status == "cancelled":
                return {"status": "cancelled", "slide_id": slide_id}
            # retry transient network / provider errors (Deepgram, edge-tts, etc.)
            msg = str(e)
            lower = msg.lower()
            if (
                "Deepgram" in msg
                or "edge" in lower
                or "timeout" in lower
                or "connect" in lower
                or "503" in msg
                or "429" in msg
            ):
                raise RetryableTaskError("TTS_PROVIDER", msg) from e
            raise NonRetryableTaskError("TTS_FAILED", msg) from e

        # Re-check cancel after long TTS work so we don't overwrite user stop
        db.refresh(narr)
        if narr.tts_status == "cancelled":
            if abs_path.is_file():
                abs_path.unlink(missing_ok=True)
            return {"status": "cancelled", "slide_id": slide_id}

        old_size = 0
        if narr.audio_key and narr.audio_key != audio_key and storage.exists(narr.audio_key):
            old_size = storage.size(narr.audio_key)
            storage.delete(narr.audio_key)

        new_size = storage.size(audio_key)
        project = db.get(Project, slide.project_id)
        if project:
            project.storage_bytes = max(0, project.storage_bytes - old_size) + new_size
            db.add(project)

        narr.audio_key = audio_key
        narr.audio_duration_ms = duration_ms
        slide.duration_ms = max(int(slide.duration_ms or 0), duration_ms)
        narr.tts_status = "ready"
        narr.tts_error = None
        narr.celery_task_id = None
        db.add(narr)
        db.add(slide)
        db.commit()
        return {"status": "ready", "slide_id": slide_id, "duration_ms": duration_ms}
    except RetryableTaskError as e:
        db.rollback()
        slide = db.get(Slide, UUID(slide_id))
        if slide and slide.narration:
            try:
                self.retry(exc=e, countdown=5 * (self.request.retries + 1))
            except self.MaxRetriesExceededError:
                narr = slide.narration
                narr.tts_status = "failed"
                narr.tts_error = e.message
                db.add(narr)
                db.commit()
        raise
    except SoftTimeLimitExceeded:
        db.rollback()
        slide = db.get(Slide, UUID(slide_id))
        if slide and slide.narration:
            narr = slide.narration
            narr.tts_status = "failed"
            narr.tts_error = "TTS timed out"
            db.add(narr)
            db.commit()
        raise
    except NonRetryableTaskError as e:
        db.rollback()
        slide = db.get(Slide, UUID(slide_id))
        if slide and slide.narration:
            narr = slide.narration
            narr.tts_status = "failed"
            narr.tts_error = e.message
            db.add(narr)
            db.commit()
        return {"status": "failed", "error": e.message}
    except Exception as e:
        db.rollback()
        slide = db.get(Slide, UUID(slide_id))
        if slide and slide.narration:
            narr = slide.narration
            narr.tts_status = "failed"
            narr.tts_error = str(e)[:500]
            db.add(narr)
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.render_video",
    max_retries=1,
    soft_time_limit=1700,
    time_limit=1800,
    acks_late=True,
)
def render_video(self, job_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    storage = get_storage()
    work_dir = Path(settings.storage_root) / "tmp" / job_id
    used_t2v = False
    try:
        job = db.get(VideoJob, UUID(job_id))
        if not job:
            raise NonRetryableTaskError("NOT_FOUND", "Job not found")
        if job.status == "cancelled":
            return {"status": "cancelled", "job_id": job_id}
        if job.status == "completed" and job.video_key:
            return {"status": "completed", "job_id": job_id}

        job.status = "processing"
        job.started_at = job.started_at or utcnow()
        job.heartbeat_at = utcnow()
        job.attempt_count = (job.attempt_count or 0) + 1
        job.stage = "validate"
        job.progress = 5
        job.celery_task_id = self.request.id
        db.add(job)
        db.commit()

        align_story_slide_durations(db, job.project_id)
        db.commit()
        slides = list(
            db.scalars(
                select(Slide)
                .options(selectinload(Slide.narration))
                .where(Slide.project_id == job.project_id)
                .order_by(Slide.order_index)
            ).all()
        )
        opts = job.options or {}
        slide_id = opts.get("slide_id")
        if slide_id:
            slides = slides_for_render(slides, slide_id)
            if not slides:
                raise NonRetryableTaskError("NOT_FOUND", "Slide not found")
        elif not slides:
            raise NonRetryableTaskError("VALIDATION", "No slides")

        media: list[SlideMedia] = []
        for s in slides:
            n = s.narration
            if not n or n.tts_status != "ready" or not n.audio_key:
                raise NonRetryableTaskError("VALIDATION", f"Slide {s.id} missing ready TTS audio")
            audio_path = storage.absolute_path(n.audio_key)
            anim = s.animation or "none"
            if anim == "wan_i2v" and not settings.wan_i2v_enabled:
                # Fall back so export still works when feature is disabled
                anim = "ken_burns"
            if anim == "wan_t2v" and not settings.wan_t2v_enabled:
                anim = "ken_burns"
            entries = s.all_image_entries()
            if anim == "wan_t2v":
                used_t2v = True
            elif not entries:
                raise NonRetryableTaskError("VALIDATION", f"Slide {s.id} has no images")
            image_paths = [storage.absolute_path(e["key"]) for e in entries]
            image_durs = [e.get("duration_ms") for e in entries]
            for p in image_paths:
                if not p.is_file():
                    raise NonRetryableTaskError("VALIDATION", f"Slide {s.id} image missing: {p.name}")
            if anim == "wan_t2v":
                cache_dir = storage.absolute_path(f"uploads/{job.project_id}/t2v_cache")
            elif anim == "wan_i2v":
                cache_dir = storage.absolute_path(f"uploads/{job.project_id}/i2v_cache")
            else:
                cache_dir = None
            cover = image_paths[0] if image_paths else Path("wan-t2v")
            media.append(
                SlideMedia(
                    slide_id=str(s.id),
                    image_path=cover,
                    image_paths=image_paths,
                    image_durations_ms=image_durs,
                    audio_path=audio_path,
                    text=n.text or "",
                    duration_ms=effective_duration_ms(s, n),
                    transition=s.transition or "fade",
                    animation=anim,
                    motion_prompt=getattr(s, "motion_prompt", None) or "",
                    i2v_cache_dir=cache_dir,
                    subtitle_cues=load_cues(audio_path),
                )
            )

        opts = job.options or {}
        project = db.get(Project, job.project_id)
        bgm_path = _background_music_path(db, storage, project, opts)

        # Resolve canvas size from job quality + aspect ratio
        quality = str(opts.get("quality") or "full")
        try:
            preset = resolve_aspect_ratio(opts.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
            qw, qh, qcrf, qfps = canvas_for_quality(preset, quality)
            render_w = int(opts.get("width") or qw)
            render_h = int(opts.get("height") or qh)
            crf = int(opts.get("crf") or qcrf)
            fps = int(opts.get("fps") or qfps)
        except ValueError:
            render_w = int(opts.get("width") or settings.video_width)
            render_h = int(opts.get("height") or settings.video_height)
            crf = int(opts.get("crf") or 20)
            fps = int(opts.get("fps") or settings.video_fps)
        x264_preset = str(opts.get("x264_preset") or ("veryfast" if quality == "draft" else "medium"))

        video_key = f"uploads/{job.project_id}/videos/{job.id}.mp4"
        thumb_key = f"uploads/{job.project_id}/thumbnails/{job.id}.jpg"
        output_path = storage.absolute_path(video_key)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def on_progress(p: int, stage: str) -> None:
            j = db.get(VideoJob, UUID(job_id))
            if not j:
                return
            if j.status == "cancelled":
                raise NonRetryableTaskError("CANCELLED", "Render cancelled by user")
            j.progress = p
            j.stage = stage
            j.heartbeat_at = utcnow()
            db.add(j)
            db.commit()

        result = render_project_video(
            slides=media,
            output_path=output_path,
            work_dir=work_dir,
            options=RenderOptions(
                width=render_w,
                height=render_h,
                fps=fps,
                crf=crf,
                x264_preset=x264_preset,
                include_subtitles=bool(opts.get("include_subtitles", True)),
                caption_style=str(opts.get("caption_style") or "auto"),
                aspect_ratio=str(opts.get("aspect_ratio") or "") or None,
                bgm_path=bgm_path,
                bgm_volume=float(opts.get("background_music_volume", 0.15)),
                fade_s=settings.fade_s,
                zoom_end=settings.ken_burns_zoom_end,
            ),
            progress_cb=on_progress,
        )

        # Copy thumbnail to storage key
        thumb_dest = storage.absolute_path(thumb_key)
        thumb_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.thumbnail_path, thumb_dest)

        job = db.get(VideoJob, UUID(job_id))
        project = db.get(Project, job.project_id)
        vsize = storage.size(video_key) if storage.exists(video_key) else 0
        tsize = storage.size(thumb_key) if storage.exists(thumb_key) else 0
        if project:
            project.storage_bytes += vsize + tsize
            db.add(project)

        job.status = "completed"
        job.progress = 100
        job.stage = "finalize"
        job.video_key = video_key
        job.thumbnail_key = thumb_key
        job.duration_ms = result.duration_ms
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.error_code = None
        job.error_message = None
        db.add(job)
        db.commit()

        # Retention: keep last N completed
        completed = db.scalars(
            select(VideoJob)
            .where(VideoJob.project_id == job.project_id, VideoJob.status == "completed")
            .order_by(VideoJob.created_at.desc())
        ).all()
        for old in completed[settings.keep_completed_jobs :]:
            for key in [old.video_key, old.thumbnail_key]:
                if key and storage.exists(key):
                    sz = storage.size(key)
                    storage.delete(key)
                    if project:
                        project.storage_bytes = max(0, project.storage_bytes - sz)
            old.video_key = None
            old.thumbnail_key = None
            db.add(old)
        if project:
            db.add(project)
        db.commit()

        return {"status": "completed", "job_id": job_id, "video_key": video_key}
    except SoftTimeLimitExceeded:
        _fail_job(db, job_id, "TIMEOUT", "Render exceeded time limit")
        raise
    except NonRetryableTaskError as e:
        if e.code == "CANCELLED":
            # already marked cancelled by API; don't overwrite as failed
            return {"status": "cancelled", "job_id": job_id}
        _fail_job(db, job_id, e.code, e.message, e.details)
        return {"status": "failed", "error": e.message}
    except RetryableTaskError as e:
        try:
            raise self.retry(exc=e, countdown=15)
        except self.MaxRetriesExceededError:
            _fail_job(db, job_id, e.code, e.message, e.details)
            return {"status": "failed", "error": e.message}
    except Exception as e:
        _fail_job(db, job_id, "RENDER_FAILED", str(e)[:500], {"trace": traceback.format_exc()[-2000:]})
        # one retry for unexpected
        if self.request.retries < 1:
            raise self.retry(exc=e, countdown=10)
        return {"status": "failed", "error": str(e)}
    finally:
        if used_t2v:
            try:
                from app.services.wan_t2v import unload_t2v

                unload_t2v()
            except Exception:
                pass
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        db.close()


def _background_music_path(db, storage, project: Project | None, opts: dict):
    """Use the chosen music asset, or the generated ACE-Step track for this project."""
    bgm_id = opts.get("background_music_asset_id")
    if bgm_id and project is not None:
        asset = db.get(MusicAsset, UUID(str(bgm_id)))
        if asset and asset.project_id == project.id:
            path = storage.absolute_path(asset.storage_key)
            if path.is_file():
                return path
    if project is None:
        return None
    mode = ((project.settings or {}).get("story") or {}).get("music_mode")
    if mode == "none":
        return None
    key = music_storage_key(project.id)
    if not storage.exists(key):
        return None
    path = storage.absolute_path(key)
    return path if path.is_file() else None


def _fail_job(db, job_id: str, code: str, message: str, details: dict | None = None) -> None:
    try:
        job = db.get(VideoJob, UUID(job_id))
        if not job or job.status == "completed":
            return
        job.status = "failed"
        job.error_code = code
        job.error_message = message
        job.error_details = details
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()


@celery_app.task(name="app.workers.tasks.generate_project_images")
def generate_project_images(job_id: str) -> dict:
    """Draw Qwen-Image-2.1 stills. Runs on the default queue."""
    from app.services.image_job import execute_image_job

    execute_image_job(UUID(job_id))
    return {"job_id": job_id}


@celery_app.task(name="app.workers.tasks.reclaim_stuck_jobs")
def reclaim_stuck_jobs() -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(seconds=settings.render_hard_limit_s + settings.stuck_job_grace_s)
        stuck = db.scalars(
            select(VideoJob).where(VideoJob.status == "processing", VideoJob.started_at < cutoff)
        ).all()
        count = 0
        for job in stuck:
            job.status = "failed"
            job.error_code = "STUCK_RECLAIMED"
            job.error_message = "Job exceeded maximum processing time without completion"
            job.finished_at = utcnow()
            db.add(job)
            count += 1
        # Also reclaim stuck TTS
        narr_stuck = db.scalars(
            select(Narration).where(Narration.tts_status == "processing")
        ).all()
        # without started_at on narrations, only reclaim if very old updated_at
        tts_cutoff = utcnow() - timedelta(minutes=10)
        for n in narr_stuck:
            if n.updated_at and n.updated_at.replace(tzinfo=timezone.utc) < tts_cutoff:
                n.tts_status = "failed"
                n.tts_error = "TTS stuck and reclaimed"
                db.add(n)
                count += 1
        db.commit()
        return {"reclaimed": count}
    finally:
        db.close()
