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


def build_export_readiness(project: _ProjectLike, slides: list[Any]) -> ExportReadinessOut:
    missing_images: list[ExportCheckIssue] = []
    empty_narration: list[ExportCheckIssue] = []
    missing_tts: list[ExportCheckIssue] = []
    tts_in_progress: list[ExportCheckIssue] = []
    tts_failed: list[ExportCheckIssue] = []

    for s in slides:
        order = s.order_index + 1
        if not s.all_image_keys():
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

    # Wan2.1 AI motion: warn when slides use wan_i2v without a real backend
    wan_slides: list[ExportCheckIssue] = []
    wan_real = False
    wan_mock = False
    wan_error: str | None = None
    try:
        from app.services.wan_i2v import resolve_backend, wan_i2v_status

        status = wan_i2v_status()
        wan_real = bool(status.get("real_ai"))
        wan_mock = bool(status.get("mock"))
        wan_error = status.get("error")
        _ = resolve_backend  # noqa: F841 — imported for clarity
    except Exception as e:
        wan_error = str(e)

    for s in slides:
        anim = getattr(s, "animation", None) or "none"
        if anim == "wan_i2v":
            order = s.order_index + 1
            if not wan_real:
                wan_slides.append(
                    ExportCheckIssue(
                        slide_id=s.id,
                        order=order,
                        message=(
                            f"Slide {order} uses AI Motion but Wan2.1 is not configured "
                            f"({wan_error or ('mock zoom only' if wan_mock else 'no backend')}). "
                            "Set FAL_KEY in .env for real video, or switch animation to Ken Burns."
                        ),
                    )
                )

    has_slides_ok = len(slides) > 0
    checks = [
        ExportCheckItem(
            id="has_slides",
            ok=has_slides_ok,
            label="Project has at least one slide",
            severity="error",
            count=0 if has_slides_ok else 1,
            issues=[]
            if has_slides_ok
            else [ExportCheckIssue(message="Add slides before exporting")],
        ),
        ExportCheckItem(
            id="images",
            ok=len(missing_images) == 0 and has_slides_ok,
            label="Every slide has an image",
            severity="error",
            count=len(missing_images),
            issues=missing_images,
        ),
        ExportCheckItem(
            id="narration",
            ok=len(empty_narration) == 0 and has_slides_ok,
            label="Every slide has narration text",
            severity="error",
            count=len(empty_narration),
            issues=empty_narration,
        ),
        ExportCheckItem(
            id="tts",
            ok=len(missing_tts) == 0 and len(tts_failed) == 0 and has_slides_ok,
            label="Every slide has ready TTS audio",
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
            label="Wan2.1 AI Motion configured (FAL_KEY / GPU)"
            if wan_slides
            else (
                "Wan2.1 AI Motion ready"
                if wan_real
                else "Wan2.1 AI Motion (optional)"
            ),
            # Block export when user asked for AI motion but only mock/unconfigured
            severity="error" if wan_slides else "info",
            count=len(wan_slides),
            issues=wan_slides,
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
