"""Fit slide images to a project canvas using Pillow — scale + pad, never crop."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from app.services.aspect_ratios import AspectRatioPreset, image_matches_aspect


@dataclass(frozen=True)
class FitResult:
    data: bytes
    ext: str  # .jpg | .png | .webp
    width: int
    height: int
    was_fitted: bool
    source_width: int
    source_height: int


def _open_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    # Honor EXIF orientation from phones/cameras
    img = ImageOps.exif_transpose(img)
    return img


def _scale_to_fit(img: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """
    Scale image so it fits entirely inside canvas_w × canvas_h (no crop).
    Preserves aspect ratio; result may be smaller than the canvas on one axis.
    """
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid image dimensions")
    scale = min(canvas_w / w, canvas_h / h)
    # Avoid upscaling small images past canvas (still fine if slightly larger sources)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    # Even dimensions for video pipelines
    new_w = max(2, new_w - (new_w % 2))
    new_h = max(2, new_h - (new_h % 2))
    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _pad_to_canvas(
    img: Image.Image,
    canvas_w: int,
    canvas_h: int,
    *,
    fill: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Center image on a solid canvas (letterbox / pillarbox). Never crops content."""
    canvas_w = max(2, canvas_w - (canvas_w % 2))
    canvas_h = max(2, canvas_h - (canvas_h % 2))
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (*fill, 255))
        layer = img.convert("RGBA")
    else:
        canvas = Image.new("RGB", (canvas_w, canvas_h), fill)
        layer = img.convert("RGB")
    x = max(0, (canvas_w - layer.width) // 2)
    y = max(0, (canvas_h - layer.height) // 2)
    canvas.paste(layer, (x, y), layer if layer.mode == "RGBA" else None)
    return canvas


def _encode(img: Image.Image, preferred_ext: str) -> tuple[bytes, str]:
    """Encode fitted image. Prefer JPEG for photos; keep PNG when transparency is needed."""
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    ext = preferred_ext.lower()
    buf = io.BytesIO()

    if has_alpha and ext in {".png", ".webp"}:
        out = img.convert("RGBA")
        if ext == ".webp":
            out.save(buf, format="WEBP", quality=90, method=4)
            return buf.getvalue(), ".webp"
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), ".png"

    out = img.convert("RGB")
    if ext == ".webp":
        out.save(buf, format="WEBP", quality=90, method=4)
        return buf.getvalue(), ".webp"
    out.save(buf, format="JPEG", quality=92, optimize=True, progressive=True)
    return buf.getvalue(), ".jpg"


def fit_image_to_aspect(
    data: bytes,
    preset: AspectRatioPreset,
    *,
    preferred_ext: str = ".jpg",
    max_long_edge: int | None = None,
) -> FitResult:
    """
    Fit image to the project canvas by **scaling + padding only** (no crop).

    - Full original content is preserved (letterboxed if aspect differs).
    - Output size is the preset canvas (e.g. 1920×1080 for 16:9).
    - If already matching ratio and within size, may still normalize to canvas
      for consistent export sizing.
    """
    img = _open_image(data)
    src_w, src_h = img.size
    canvas_w = preset.width
    canvas_h = preset.height
    if max_long_edge:
        # Keep canvas aspect; only shrink if requested cap is below preset
        long_edge = max(canvas_w, canvas_h)
        if max_long_edge < long_edge:
            scale = max_long_edge / long_edge
            canvas_w = max(2, int(round(canvas_w * scale)) // 2 * 2)
            canvas_h = max(2, int(round(canvas_h * scale)) // 2 * 2)

    already_ok = (
        image_matches_aspect(src_w, src_h, preset)
        and src_w == canvas_w
        and src_h == canvas_h
    )
    if already_ok:
        return FitResult(
            data=data,
            ext=preferred_ext if preferred_ext in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg",
            width=src_w,
            height=src_h,
            was_fitted=False,
            source_width=src_w,
            source_height=src_h,
        )

    scaled = _scale_to_fit(img, canvas_w, canvas_h)
    canvas = _pad_to_canvas(scaled, canvas_w, canvas_h, fill=(0, 0, 0))

    out_data, out_ext = _encode(canvas, preferred_ext)
    return FitResult(
        data=out_data,
        ext=out_ext if out_ext != ".jpeg" else ".jpg",
        width=canvas_w,
        height=canvas_h,
        was_fitted=True,
        source_width=src_w,
        source_height=src_h,
    )
