from __future__ import annotations

import imghdr
from pathlib import Path

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a"}
ALLOWED_AUDIO_MIME = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}

# Magic bytes
PNG_SIG = b"\x89PNG\r\n\x1a\n"
JPEG_SIG = b"\xff\xd8\xff"
WEBP_RIFF = b"RIFF"
WEBP_WEBP = b"WEBP"
ID3 = b"ID3"
MP3_FF = b"\xff\xfb"
WAV = b"RIFF"


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_image_bytes(data: bytes, filename: str) -> str:
    ext = extension_of(filename)
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError(f"Unsupported image extension: {ext}")
    if data.startswith(PNG_SIG):
        if ext not in {".png"}:
            # allow renaming to png-like
            pass
        return ".png" if ext == ".png" else ext
    if data.startswith(JPEG_SIG):
        return ".jpg" if ext in {".jpg", ".jpeg"} else ext
    if len(data) > 12 and data[:4] == WEBP_RIFF and data[8:12] == WEBP_WEBP:
        return ".webp"
    # fallback via imghdr
    kind = imghdr.what(None, h=data)
    if kind == "png" and ext == ".png":
        return ext
    if kind in {"jpeg", "jpg"} and ext in {".jpg", ".jpeg"}:
        return ext
    raise ValueError("Image content does not match allowed types (png/jpeg/webp)")


def validate_audio_bytes(data: bytes, filename: str) -> str:
    ext = extension_of(filename)
    if ext not in ALLOWED_AUDIO_EXT:
        raise ValueError(f"Unsupported audio extension: {ext}")
    if data.startswith(ID3) or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return ".wav"
    if ext in ALLOWED_AUDIO_EXT and len(data) > 100:
        return ext
    raise ValueError("Audio content does not match allowed types")


def validate_video_bytes(data: bytes, filename: str) -> str:
    """Basic extension + magic-byte checks for clipper source videos."""
    ext = extension_of(filename)
    if ext not in ALLOWED_VIDEO_EXT:
        raise ValueError(f"Unsupported video extension: {ext}. Use mp4, mov, webm, or mkv.")
    if len(data) < 12:
        raise ValueError("Video file is empty or too small")
    # ISO BMFF (mp4/mov/m4v): ....ftyp
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return ext if ext in {".mp4", ".mov", ".m4v", ".mkv"} else ".mp4"
    # WebM / Matroska: EBML header
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return ext if ext in {".webm", ".mkv"} else ".webm"
    # RIFF AVI
    if data.startswith(b"RIFF") and data[8:12] == b"AVI ":
        return ".avi" if ext == ".avi" else ext
    # Trust extension if file is large enough (some containers vary)
    if len(data) > 1024 and ext in ALLOWED_VIDEO_EXT:
        return ext
    raise ValueError("Video content does not look like a supported media file")
