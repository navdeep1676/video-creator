"""Video aspect-ratio presets for long-form, short-form, and square exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AspectRatioPreset:
    id: str
    label: str
    description: str
    width: int
    height: int
    category: str  # long | short | square | social

    @property
    def ratio(self) -> float:
        return self.width / self.height


# Even dimensions for H.264 (yuv420p). 1080-class quality.
ASPECT_RATIO_PRESETS: dict[str, AspectRatioPreset] = {
    "16:9": AspectRatioPreset(
        id="16:9",
        label="Landscape 16:9",
        description="YouTube, courses, desktop long-form",
        width=1920,
        height=1080,
        category="long",
    ),
    "9:16": AspectRatioPreset(
        id="9:16",
        label="Portrait 9:16",
        description="YouTube Shorts, TikTok, Instagram Reels",
        width=1080,
        height=1920,
        category="short",
    ),
    "1:1": AspectRatioPreset(
        id="1:1",
        label="Square 1:1",
        description="Instagram feed, carousel posts",
        width=1080,
        height=1080,
        category="square",
    ),
    "4:5": AspectRatioPreset(
        id="4:5",
        label="Vertical 4:5",
        description="Instagram portrait feed",
        width=1080,
        height=1350,
        category="social",
    ),
}

DEFAULT_ASPECT_RATIO = "16:9"
ASPECT_RATIO_IDS = frozenset(ASPECT_RATIO_PRESETS.keys())

# Relative tolerance when checking upload dimensions (handles 720p/1080p/etc.)
ASPECT_RATIO_TOLERANCE = 0.04


def resolve_aspect_ratio(aspect_ratio: str | None) -> AspectRatioPreset:
    """Return a known preset; unknown values fall back to landscape 16:9."""
    key = (aspect_ratio or DEFAULT_ASPECT_RATIO).strip()
    if key not in ASPECT_RATIO_PRESETS:
        if aspect_ratio is None or not str(aspect_ratio).strip():
            return ASPECT_RATIO_PRESETS[DEFAULT_ASPECT_RATIO]
        raise ValueError(
            f"Unknown aspect_ratio '{aspect_ratio}'. "
            f"Choose one of: {', '.join(sorted(ASPECT_RATIO_PRESETS))}"
        )
    return ASPECT_RATIO_PRESETS[key]


def project_aspect_ratio(settings: dict[str, Any] | None) -> AspectRatioPreset:
    """Read aspect ratio from project.settings JSONB."""
    raw = None
    if isinstance(settings, dict):
        raw = settings.get("aspect_ratio")
    try:
        return resolve_aspect_ratio(str(raw) if raw else None)
    except ValueError:
        return ASPECT_RATIO_PRESETS[DEFAULT_ASPECT_RATIO]


def image_matches_aspect(
    width: int,
    height: int,
    preset: AspectRatioPreset,
    *,
    tolerance: float = ASPECT_RATIO_TOLERANCE,
) -> bool:
    """True if image width/height is within tolerance of the preset ratio."""
    if width <= 0 or height <= 0:
        return False
    actual = width / height
    expected = preset.ratio
    return abs(actual - expected) / expected <= tolerance


def aspect_mismatch_message(
    filename: str,
    width: int,
    height: int,
    preset: AspectRatioPreset,
) -> str:
    actual = f"{width}:{height}" if height else "?"
    return (
        f"{filename} is {width}×{height} (≈{actual} ratio), but this project only accepts "
        f"{preset.id} images (e.g. {preset.width}×{preset.height} for {preset.label}). "
        f"Crop or export slides to {preset.id} before uploading."
    )


# Render quality: full = native preset canvas; draft = ~720p long-edge for fast preview
RENDER_QUALITY_FULL = "full"
RENDER_QUALITY_DRAFT = "draft"
RENDER_QUALITY_IDS = frozenset({RENDER_QUALITY_FULL, RENDER_QUALITY_DRAFT})


def canvas_for_quality(
    preset: AspectRatioPreset,
    quality: str | None = RENDER_QUALITY_FULL,
) -> tuple[int, int, int, int]:
    """
    Return (width, height, crf, fps) for a quality tier.

    - full: preset canvas, CRF 20, 30 fps
    - draft: long edge 720, CRF 28, 24 fps (faster encode, smaller files)
    """
    q = (quality or RENDER_QUALITY_FULL).strip().lower()
    if q not in RENDER_QUALITY_IDS:
        q = RENDER_QUALITY_FULL

    if q == RENDER_QUALITY_DRAFT:
        # True 720p-class: short side 720 → 1280×720 (16:9), 720×1280 (9:16), etc.
        short = min(preset.width, preset.height)
        scale = 720 / short
        w = max(2, int(round(preset.width * scale)) // 2 * 2)
        h = max(2, int(round(preset.height * scale)) // 2 * 2)
        return w, h, 28, 24

    return preset.width, preset.height, 20, 30


def subtitle_style_for(width: int, height: int) -> tuple[int, int]:
    """
    Scale ASS font size and bottom margin for the canvas.
    Portrait needs larger type and more bottom margin for mobile safe areas.
    """
    # Reference: 1920×1080 → font 34, margin_v 100
    short_side = min(width, height)
    scale = short_side / 1080.0
    font_size = max(28, int(round(34 * scale)))
    # Extra margin on tall frames (shorts) so text sits above UI chrome
    base_margin = 100 if height <= width else 160
    margin_v = max(80, int(round(base_margin * scale)))
    return font_size, margin_v
