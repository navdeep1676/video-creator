from app.services.live_sync import encode_sync_event, sync_delta


def test_first_sync_sends_data_without_reloading_the_story():
    current = {"job": {"status": "running"}, "music": None, "story_version": "a:1:1"}
    delta = sync_delta(None, current)
    assert delta is not None
    assert delta["job"]["status"] == "running"
    assert "reload_story" not in delta


def test_unchanged_sync_sends_nothing():
    current = {"job": {"status": "running"}, "story_version": "a:1:1"}
    assert sync_delta(current, dict(current)) is None


def test_story_text_change_asks_for_one_reload():
    previous = {"job": {"status": "running"}, "story_version": "a:0:0"}
    current = {"job": {"status": "succeeded"}, "story_version": "a:20:4"}
    delta = sync_delta(previous, current)
    assert delta is not None
    assert delta["reload_story"] is True
    assert delta["job"]["status"] == "succeeded"


def test_progress_change_does_not_reload_the_story():
    previous = {"job": {"status": "running", "progress": 10}, "story_version": "a:1:1"}
    current = {"job": {"status": "running", "progress": 40}, "story_version": "a:1:1"}
    delta = sync_delta(previous, current)
    assert delta is not None
    assert delta["job"]["progress"] == 40
    assert "reload_story" not in delta


def test_event_frame_is_one_sse_message():
    frame = encode_sync_event({"job": {"status": "queued"}})
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert "\n\n" not in frame[:-2]
