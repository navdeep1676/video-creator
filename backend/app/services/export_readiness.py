"""Pre-render export checklist: images, narration, TTS status."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.schemas.common import (
    ExportCheckIssue,
    ExportCheckItem,
    ExportReadinessOut,
)
from app.services.aspect_ratios import project_aspect_ratio


class _NarrationLike(Protocol):
    text: str | None
    tts_status: str | None
    audio_key: str | None


class _SlideLike(Protocol):
    id: UUID
    order_index: int
    narration: _NarrationLike | None

    def all_image_keys(self) -> list[str]: ...


class _ProjectLike(Protocol):
    id: UUID
    settings: dict[str, Any] | None


def slides_for_render(slides: list[Any], slide_id: UUID | str | None) -> list[Any]:
    """Keep every slide, or only the one requested for a single-slide video."""
    if not slide_id:
        return list(slides)
    wanted = str(slide_id)
    return [s for s in slides if str(s.id) == wanted]


def build_export_readiness(
    project: _ProjectLike,
    slides: list[Any],
    *,
    single_slide: bool = False,
) -> ExportReadinessOut:
    missing_images: list[ExportCheckIssue] = []
    empty_narration: list[ExportCheckIssue] = []
    missing_tts: list[ExportCheckIssue] = []
    tts_in_progress: list[ExportCheckIssue] = []
    tts_failed: list[ExportCheckIssue] = []

    for s in slides:
        order = s.order_index + 1
        if not s.all_image_keys() and (getattr(s, "animation", None) or "none") != "wan_t2v":
            missing_images.append(
                ExportCheckIssue(
                    slide_id=s.id,
                    order=order,
                    message=f"Slide {order} has no images",
                )
            )
        n = s.narration
        text = (n.text or "").strip() if n else ""
        if not text:
            empty_narration.append(
                ExportCheckIssue(
                    slide_id=s.id,
                    order=order,
                    message=f"Slide {order} has empty narration",
                )
            )
        if n and n.tts_status in {"queued", "processing"}:
            tts_in_progress.append(
                ExportCheckIssue(
                    slide_id=s.id,
                    order=order,
                    message=f"Slide {order} TTS is still {n.tts_status}",
                )
            )
        elif n and n.tts_status in {"failed", "cancelled"}:
            tts_failed.append(
                ExportCheckIssue(
                    slide_id=s.id,
                    order=order,
                    message=f"Slide {order} TTS {n.tts_status}",
                )
            )
        elif not n or n.tts_status != "ready" or not n.audio_key:
            if text:
                missing_tts.append(
                    ExportCheckIssue(
                        slide_id=s.id,
                        order=order,
                        message=f"Slide {order} needs voice generation",
                    )
                )

    # Wan2.2 TI2V 5B covers AI Motion (still + prompt) and text-to-video.
    wan_slides: list[ExportCheckIssue] = []
    t2v_slides: list[ExportCheckIssue] = []
    t2v_real = False
    t2v_mock = False
    t2v_error: str | None = None
    try:
        from app.services.wan_t2v import wan_t2v_status

        t2v_status = wan_t2v_status()
        t2v_real = bool(t2v_status.get("real_ai"))
        t2v_mock = bool(t2v_status.get("mock"))
        t2v_error = t2v_status.get("error")
    except Exception as e:
        t2v_error = str(e)

    for s in slides:
        anim = getattr(s, "animation", None) or "none"
        if anim not in {"wan_t2v", "wan_i2v"} or t2v_real:
            continue
        order = s.order_index + 1
        issue = ExportCheckIssue(
            slide_id=s.id,
            order=order,
            message=(
                f"Slide {order} uses Wan2.2 TI2V 5B but it is not configured "
                f"({t2v_error or ('mock clip only' if t2v_mock else 'no backend')}). "
                "Install Wan-AI/Wan2.2-TI2V-5B-Diffusers or point WAN_T2V_CLI_SCRIPT at Wan2.2 generate.py."
            ),
        )
        if anim == "wan_i2v":
            wan_slides.append(issue)
        else:
            t2v_slides.append(issue)

    has_slides_ok = len(slides) > 0
    subject = "This slide" if single_slide else "Every slide"
    checks = [
        ExportCheckItem(
            id="has_slides",
            ok=has_slides_ok,
            label="Slide selected" if single_slide else "Project has at least one slide",
            severity="error",
            count=0 if has_slides_ok else 1,
            issues=[]
            if has_slides_ok
            else [
                ExportCheckIssue(
                    message="Slide not found" if single_slide else "Add slides before exporting"
                )
            ],
        ),
        ExportCheckItem(
            id="images",
            ok=len(missing_images) == 0 and has_slides_ok,
            label=f"{subject} has an image",
            severity="error",
            count=len(missing_images),
            issues=missing_images,
        ),
        ExportCheckItem(
            id="narration",
            ok=len(empty_narration) == 0 and has_slides_ok,
            label=f"{subject} has narration text",
            severity="error",
            count=len(empty_narration),
            issues=empty_narration,
        ),
        ExportCheckItem(
            id="tts",
            ok=len(missing_tts) == 0 and len(tts_failed) == 0 and has_slides_ok,
            label=f"{subject} has ready TTS audio",
            severity="error",
            count=len(missing_tts) + len(tts_failed),
            issues=missing_tts + tts_failed,
        ),
        ExportCheckItem(
            id="tts_idle",
            ok=len(tts_in_progress) == 0,
            label="No TTS jobs still running",
            severity="warning" if tts_in_progress else "info",
            count=len(tts_in_progress),
            issues=tts_in_progress,
        ),
        ExportCheckItem(
            id="wan_i2v",
            ok=len(wan_slides) == 0,
            label="Wan2.2 TI2V 5B image motion configured"
            if wan_slides
            else (
                "Wan2.2 TI2V 5B image motion ready"
                if t2v_real
                else "Wan2.2 TI2V 5B image motion (optional)"
            ),
            # Block export when user asked for AI motion but only mock/unconfigured
            severity="error" if wan_slides else "info",
            count=len(wan_slides),
            issues=wan_slides,
        ),
        ExportCheckItem(
            id="wan_t2v",
            ok=len(t2v_slides) == 0,
            label="Wan2.2 TI2V 5B text motion configured"
            if t2v_slides
            else (
                "Wan2.2 TI2V 5B text motion ready"
                if t2v_real
                else "Wan2.2 TI2V 5B text motion (optional)"
            ),
            severity="error" if t2v_slides else "info",
            count=len(t2v_slides),
            issues=t2v_slides,
        ),
    ]

    blocking = [c for c in checks if not c.ok and c.severity == "error"]
    ready = has_slides_ok and len(blocking) == 0 and len(tts_in_progress) == 0

    preset = project_aspect_ratio(project.settings if isinstance(project.settings, dict) else None)
    recommended = (
        "shorts" if preset.category in {"short", "social"} or preset.height > preset.width else "youtube"
    )

    return ExportReadinessOut(
        ready=ready,
        project_id=project.id,
        slide_count=len(slides),
        summary={
            "missing_images": len(missing_images),
            "empty_narration": len(empty_narration),
            "missing_tts": len(missing_tts) + len(tts_failed),
            "tts_in_progress": len(tts_in_progress),
        },
        checks=checks,
        recommended_caption_style=recommended,
    )
