"""Single-slide render scope: only the chosen slide is checked and exported."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.export_readiness import build_export_readiness, slides_for_render


def _slide(order: int, *, ready: bool, animation: str = "ken_burns"):
    return SimpleNamespace(
        id=uuid4(),
        order_index=order,
        animation=animation,
        narration=SimpleNamespace(
            text="A line of narration.",
            tts_status="ready" if ready else "pending",
            audio_key="audio.mp3" if ready else None,
        ),
        all_image_keys=lambda: ["slide.png"],
    )


def test_slides_for_render_keeps_one_slide():
    first = _slide(0, ready=True)
    second = _slide(1, ready=False)
    assert slides_for_render([first, second], None) == [first, second]
    assert slides_for_render([first, second], second.id) == [second]
    assert slides_for_render([first, second], str(second.id)) == [second]
    assert slides_for_render([first, second], uuid4()) == []


def test_single_slide_readiness_ignores_other_slides():
    ready = _slide(0, ready=True)
    blocked = _slide(1, ready=False)
    project = SimpleNamespace(id=uuid4(), settings={"aspect_ratio": "16:9"})

    full = build_export_readiness(project, [ready, blocked])
    assert full.ready is False
    assert full.slide_count == 2
    assert full.summary["missing_tts"] == 1

    one = build_export_readiness(
        project,
        slides_for_render([ready, blocked], ready.id),
        single_slide=True,
    )
    assert one.ready is True
    assert one.slide_count == 1
    labels = {c.id: c.label for c in one.checks}
    assert labels["images"] == "This slide has an image"
    assert labels["tts"] == "This slide has ready TTS audio"
