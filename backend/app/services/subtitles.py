from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

# ASS PrimaryColour is &HAABBGGRR (alpha, blue, green, red)
_ASS_WHITE = "&H00FFFFFF"
_ASS_YELLOW = "&H0000FFFF"  # pure yellow


def cues_path_for(audio_path: Path | str) -> Path:
    """Sidecar path for timed subtitle cues next to an audio file."""
    p = Path(audio_path)
    return p.with_suffix(".cues.json")


def write_cues(audio_path: Path | str, cues: list[dict[str, Any]], provider: str = "") -> Path:
    path = cues_path_for(audio_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"provider": provider, "cues": cues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_cues(audio_path: Path | str) -> list[dict[str, Any]]:
    path = cues_path_for(audio_path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    cues = data.get("cues") if isinstance(data, dict) else None
    if not isinstance(cues, list):
        return []
    out: list[dict[str, Any]] = []
    for c in cues:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(c.get("start_s", 0))
            end = float(c.get("end_s", start + 0.5))
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 0.35
        out.append({"start_s": max(0.0, start), "end_s": end, "text": text})
    return out


def group_words_into_cues(
    words: list[dict[str, Any]],
    *,
    max_chars: int = 42,
    max_words: int = 7,
    max_gap_s: float = 0.35,
) -> list[dict[str, Any]]:
    """
    Collapse word-level timings into readable subtitle lines that track speech.
    Each word: {text, start_s, end_s}
    """
    if not words:
        return []

    cues: list[dict[str, Any]] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end: float = 0.0

    def flush() -> None:
        nonlocal buf_text, buf_start, buf_end
        if not buf_text or buf_start is None:
            buf_text = []
            buf_start = None
            return
        text = " ".join(buf_text).strip()
        if text:
            cues.append({"start_s": buf_start, "end_s": max(buf_end, buf_start + 0.3), "text": text})
        buf_text = []
        buf_start = None

    for w in words:
        text = str(w.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(w["start_s"])
            end = float(w["end_s"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            end = start + 0.12

        if buf_start is None:
            buf_text = [text]
            buf_start = start
            buf_end = end
            continue

        gap = start - buf_end
        candidate = " ".join(buf_text + [text])
        # New sentence (capitalized word after a pause) → new cue
        likely_sentence_break = (
            gap > 0.18
            and len(buf_text) >= 2
            and text[:1].isupper()
            and text[:1].isalpha()
        )
        if (
            likely_sentence_break
            or gap > max_gap_s
            or len(candidate) > max_chars
            or len(buf_text) >= max_words
        ):
            flush()
            buf_text = [text]
            buf_start = start
            buf_end = end
        else:
            buf_text.append(text)
            buf_end = end

    flush()
    return cues

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def split_phrases(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    if not parts:
        parts = [text]

    # Further split long sentences on commas / semicolons
    refined: list[str] = []
    for part in parts:
        if len(part) <= 56:
            refined.append(part)
            continue
        chunks = re.split(r"(?<=[,;:])\s+", part)
        buf = ""
        for ch in chunks:
            if not buf:
                buf = ch
            elif len(buf) + 1 + len(ch) <= 56:
                buf = f"{buf} {ch}"
            else:
                refined.append(buf)
                buf = ch
        if buf:
            refined.append(buf)
    return refined or [text]


def estimate_phrase_cues(text: str, duration_s: float) -> list[dict[str, Any]]:
    """Proportional phrase timings when word boundaries are unavailable (e.g. Deepgram)."""
    phrases = split_phrases(text)
    if not phrases:
        return []
    duration_s = max(0.5, float(duration_s))
    weights = [max(1, len(p.split())) for p in phrases]
    total_w = sum(weights)
    t = 0.0
    cues: list[dict[str, Any]] = []
    for i, (phrase, w) in enumerate(zip(phrases, weights)):
        if i == len(phrases) - 1:
            end = duration_s
        else:
            end = t + duration_s * (w / total_w)
        # slight lead-in padding so last word is readable
        cues.append({"start_s": t, "end_s": max(end, t + 0.35), "text": phrase})
        t = end
    if cues:
        cues[-1]["end_s"] = max(cues[-1]["end_s"], duration_s)
    return cues


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _iter_cue_windows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten timeline entries into absolute start/end/text cues."""
    out: list[dict[str, Any]] = []
    for e in entries:
        slide_start = float(e.get("start_s", 0))
        slide_end = float(e.get("end_s", slide_start + 1))
        cues = e.get("cues") or []
        if cues:
            for c in cues:
                text = _clean_sub_text(str(c.get("text") or ""))
                if not text:
                    continue
                start = slide_start + float(c["start_s"])
                end = slide_start + float(c["end_s"])
                start = min(max(start, slide_start), slide_end)
                end = min(max(end, start + 0.2), slide_end + 0.05)
                out.append({"start_s": start, "end_s": end, "text": text})
        else:
            text = _clean_sub_text(str(e.get("text") or ""))
            if not text:
                continue
            out.append({"start_s": slide_start, "end_s": slide_end, "text": text})
    return out


def build_srt_from_timeline(entries: list[dict[str, Any]]) -> str:
    """
    Build SRT for full video timeline.

    Each entry:
      start_s, end_s, text,
      optional cues: list[{start_s, end_s, text}] relative to slide start
    """
    lines: list[str] = []
    for idx, c in enumerate(_iter_cue_windows(entries), start=1):
        lines.append(
            f"{idx}\n{srt_timestamp(c['start_s'])} --> {srt_timestamp(c['end_s'])}\n{c['text']}\n"
        )
    return "\n".join(lines)


def _ass_timestamp(seconds: float) -> str:
    """ASS time: H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _escape_ass_text(text: str) -> str:
    # ASS special chars
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{").replace("}", "\\}")
    text = text.replace("\n", "\\N")
    return text


def pick_subtitle_font(text: str) -> str:
    """
    Choose a font that actually has glyphs for the script.
    DejaVu has almost no Devanagari/CJK/Arabic → black boxes in burned-in subs.
    """
    for ch in text:
        o = ord(ch)
        # Devanagari (Hindi, Marathi, etc.)
        if 0x0900 <= o <= 0x097F or 0xA8E0 <= o <= 0xA8FF:
            return "Noto Sans Devanagari"
        # Bengali
        if 0x0980 <= o <= 0x09FF:
            return "Noto Sans Bengali"
        # Tamil
        if 0x0B80 <= o <= 0x0BFF:
            return "Noto Sans Tamil"
        # Telugu
        if 0x0C00 <= o <= 0x0C7F:
            return "Noto Sans Telugu"
        # Gujarati
        if 0x0A80 <= o <= 0x0AFF:
            return "Noto Sans Gujarati"
        # Gurmukhi (Punjabi)
        if 0x0A00 <= o <= 0x0A7F:
            return "Noto Sans Gurmukhi"
        # Kannada
        if 0x0C80 <= o <= 0x0CFF:
            return "Noto Sans Kannada"
        # Malayalam
        if 0x0D00 <= o <= 0x0D7F:
            return "Noto Sans Malayalam"
        # Arabic / Urdu
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF:
            return "Noto Sans Arabic"
        # CJK
        if (
            0x3040 <= o <= 0x30FF  # Hiragana/Katakana
            or 0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF
            or 0xF900 <= o <= 0xFAFF
            or 0xAC00 <= o <= 0xD7AF  # Hangul
        ):
            return "Noto Sans CJK JP"
        # Thai
        if 0x0E00 <= o <= 0x0E7F:
            return "Noto Sans Thai"
    return "Noto Sans"


def build_ass_from_timeline(
    entries: list[dict[str, Any]],
    *,
    play_res_x: int = 1920,
    play_res_y: int = 1080,
    font_size: int = 34,
    margin_v: int = 100,
    margin_l: int = 80,
    margin_r: int = 80,
    outline: float = 0.0,
    shadow: float = 0.0,
    seed: int | None = None,
    font_name: str | None = None,
) -> str:
    """
    ASS subtitles for burn-in:
    - multi-script fonts (Hindi/Devanagari etc. — not DejaVu)
    - platform-safe margins (YouTube vs Shorts style packs)
    - each cue randomly white or yellow
    """
    rng = random.Random(seed)
    cues = _iter_cue_windows(entries)

    # Default body font; per-cue overrides via \fn for non-Latin scripts
    default_font = font_name or "Noto Sans"
    bord = max(0.0, float(outline))
    shad = max(0.0, float(shadow))
    ml = max(0, int(margin_l))
    mr = max(0, int(margin_r))
    mv = max(0, int(margin_v))

    def _style_line(name: str, colour: str) -> str:
        # Alignment 2 = bottom-center; MarginL/R/V define safe area
        return (
            f"Style: {name},{default_font},{font_size},{colour},&H000000FF,"
            f"&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{bord},{shad},2,"
            f"{ml},{mr},{mv},1"
        )

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{_style_line("Default", _ASS_WHITE)}
{_style_line("White", _ASS_WHITE)}
{_style_line("Yellow", _ASS_YELLOW)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for c in cues:
        style = rng.choice(["White", "Yellow"])
        text = _escape_ass_text(c["text"])
        font = pick_subtitle_font(c["text"])
        text = f"{{\\fn{font}\\fs{font_size}\\bord{bord}\\shad{shad}}}{text}"
        events.append(
            f"Dialogue: 0,{_ass_timestamp(c['start_s'])},{_ass_timestamp(c['end_s'])},"
            f"{style},,0,0,0,,{text}"
        )
    return header + "\n".join(events) + ("\n" if events else "")


def _clean_sub_text(text: str) -> str:
    text = text.replace("\r", "").replace("-->", "→")
    text = " ".join(part for part in text.split("\n") if part.strip())
    return text.strip()
