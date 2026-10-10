"""Progress math for the render bar. No GPU."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.ace_step import ace_step_percent
from app.services.job_control import render_job_is_stuck
from app.services.render_progress import wan_clip_update
from app.services.stage_job import job_view


def test_wan_steps_move_inside_the_scene_band():
    early, early_stage = wan_clip_update(0, 2, "step 1/50")
    late, late_stage = wan_clip_update(0, 2, "step 50/50")
    nxt, _next_stage = wan_clip_update(1, 2, "step 1/50")
    assert early < late < nxt
    assert early_stage == "wan 1/2 step 1/50"
    assert late_stage == "wan 1/2 step 50/50"
    assert nxt < 100


def test_wan_messages_use_short_labels():
    assert wan_clip_update(0, 1, "loading model Wan-AI/Wan2.2")[1] == "wan 1/1 loading model"
    assert wan_clip_update(0, 1, "using cached Wan T2V clip")[1] == "wan 1/1 cached"
    assert wan_clip_update(0, 1, "exporting video")[1] == "wan 1/1 exporting"
    assert wan_clip_update(0, 1, "sampling 81 frames @ 832x480")[1] == "wan 1/1 sampling"
    assert wan_clip_update(0, 1, "generating with backend=diffusers")[1] == "wan 1/1 starting"


def test_cached_clip_reaches_the_end_of_its_band():
    percent, _stage = wan_clip_update(0, 1, "using cached Wan T2V clip")
    assert percent == 40


def test_wan_stage_fits_the_column():
    _percent, stage = wan_clip_update(9, 12, "step 3/50 " + ("m" * 80))
    assert len(stage) <= 64
    assert stage.startswith("wan 10/12 step 3/50")


def test_a_live_wan_render_is_not_reclaimed_while_steps_are_reporting():
    now = datetime(2026, 10, 10, 18, 10, tzinfo=timezone.utc)
    started = now - timedelta(minutes=40)
    heartbeat = now - timedelta(minutes=4)
    assert (
        render_job_is_stuck(started, heartbeat, now, stale_s=1800, hard_limit_s=28800) is False
    )


def test_a_silent_render_is_reclaimed():
    now = datetime(2026, 10, 10, 18, 10, tzinfo=timezone.utc)
    started = now - timedelta(minutes=50)
    heartbeat = now - timedelta(minutes=31)
    assert render_job_is_stuck(started, heartbeat, now, stale_s=1800, hard_limit_s=28800) is True


def test_a_render_past_the_hard_limit_is_reclaimed_even_with_a_fresh_heartbeat():
    now = datetime(2026, 10, 10, 18, 10, tzinfo=timezone.utc)
    started = now - timedelta(hours=8, minutes=1)
    heartbeat = now - timedelta(minutes=1)
    assert render_job_is_stuck(started, heartbeat, now, stale_s=1800, hard_limit_s=28800) is True


def test_ace_percent_reads_a_fraction_or_a_percent():
    assert ace_step_percent({"progress": 0.4}) == 40
    assert ace_step_percent({"progress_percent": 55}) == 55
    assert ace_step_percent({"status": 0}) is None
    assert ace_step_percent({}) is None


def test_job_view_includes_progress_fields():
    moment = datetime(2026, 10, 10, tzinfo=timezone.utc)
    view = job_view(
        SimpleNamespace(
            id="abc",
            project_id="p",
            stage="images",
            status="running",
            attempts=1,
            error=None,
            progress=40,
            detail="Drawing scene 2",
            started_at=moment,
            created_at=moment,
        )
    )
    assert view["progress"] == 40
    assert view["detail"] == "Drawing scene 2"
    assert view["started_at"] == moment.isoformat()
    assert view["created_at"] == moment.isoformat()
    assert view["stage"] == "images"
