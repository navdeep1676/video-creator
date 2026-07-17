"""Caption style packs with platform-safe margins (YouTube vs Shorts UI chrome)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptionStylePack:
    id: str
    label: str
    description: str
    # Margins as fraction of PlayRes (width for L/R, height for V)
    margin_v_ratio: float
    margin_h_ratio: float
    font_scale: float
    outline: float  # ASS bord
    shadow: float
    # Soft guidance for cue wrapping when re-chunking at burn-in
    max_chars: int
    max_words: int
    # Which project categories this pack suits best
    best_for: tuple[str, ...]  # long | short | square | social | any


CAPTION_STYLE_PACKS: dict[str, CaptionStylePack] = {
    "youtube": CaptionStylePack(
        id="youtube",
        label="YouTube safe",
        description="Lower-third captions with side margins safe for long-form / landscape players.",
        margin_v_ratio=0.09,
        margin_h_ratio=0.055,
        font_scale=1.0,
        outline=0.0,
        shadow=0.0,
        max_chars=42,
        max_words=7,
        best_for=("long", "any"),
    ),
    "shorts": CaptionStylePack(
        id="shorts",
        label="Shorts safe",
        description=(
            "Extra bottom & side margins clear of Shorts / TikTok / Reels UI "
            "(username, buttons, captions strip)."
        ),
        margin_v_ratio=0.20,
        margin_h_ratio=0.11,
        font_scale=1.12,
        outline=0.0,
        shadow=0.0,
        max_chars=28,
        max_words=5,
        best_for=("short", "social", "any"),
    ),
    "auto": CaptionStylePack(
        id="auto",
        label="Auto (by format)",
        description="YouTube safe for landscape; Shorts safe for portrait / vertical formats.",
        # Values unused — resolved to youtube or shorts at runtime
        margin_v_ratio=0.09,
        margin_h_ratio=0.055,
        font_scale=1.0,
        outline=0.0,
        shadow=0.0,
        max_chars=42,
        max_words=7,
        best_for=("any",),
    ),
}

DEFAULT_CAPTION_STYLE = "auto"
CAPTION_STYLE_IDS = frozenset(CAPTION_STYLE_PACKS.keys())


def resolve_caption_style(
    style_id: str | None,
    *,
    width: int,
    height: int,
    aspect_ratio: str | None = None,
) -> CaptionStylePack:
    """
    Resolve a pack id to concrete style settings.
    `auto` picks Shorts pack for portrait canvases, YouTube for landscape/square.
    """
    key = (style_id or DEFAULT_CAPTION_STYLE).strip().lower()
    if key not in CAPTION_STYLE_PACKS:
        key = DEFAULT_CAPTION_STYLE

    pack = CAPTION_STYLE_PACKS[key]
    if pack.id != "auto":
        return pack

    # Portrait / tall → Shorts safe; otherwise YouTube safe
    ar = (aspect_ratio or "").strip()
    if ar in {"9:16", "4:5"} or height > width:
        return CAPTION_STYLE_PACKS["shorts"]
    return CAPTION_STYLE_PACKS["youtube"]


def caption_margins_px(
    pack: CaptionStylePack,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """
    Return (font_size, margin_v, margin_l, margin_r) in ASS PlayRes units.
    Font size scales with short side (1080 ref → 34) then pack font_scale.
    """
    short_side = max(1, min(width, height))
    scale = short_side / 1080.0
    base_font = max(26, int(round(34 * scale)))
    font_size = max(24, int(round(base_font * pack.font_scale)))

    margin_v = max(48, int(round(height * pack.margin_v_ratio)))
    margin_h = max(36, int(round(width * pack.margin_h_ratio)))
    # Cap so text area never collapses
    max_v = int(height * 0.35)
    max_h = int(width * 0.22)
    margin_v = min(margin_v, max_v)
    margin_h = min(margin_h, max_h)
    return font_size, margin_v, margin_h, margin_h


def caption_style_public_dict(pack: CaptionStylePack) -> dict[str, Any]:
    return {
        "id": pack.id,
        "label": pack.label,
        "description": pack.description,
        "margin_v_ratio": pack.margin_v_ratio,
        "margin_h_ratio": pack.margin_h_ratio,
        "font_scale": pack.font_scale,
        "max_chars": pack.max_chars,
        "max_words": pack.max_words,
        "best_for": list(pack.best_for),
    }
