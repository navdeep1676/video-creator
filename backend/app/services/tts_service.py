from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.subtitles import (
    estimate_phrase_cues,
    group_words_into_cues,
    write_cues,
)
from app.services.voices import (
    VOICE_BY_ID,
    VOICE_IDS,
    VOICES,
    get_voice,
    list_languages,
    list_voices,
    public_voice,
)
from app.utils.media import ffprobe_duration_ms, run_ffmpeg

logger = logging.getLogger(__name__)

# Re-export for existing imports
__all__ = [
    "VOICES",
    "VOICE_IDS",
    "VOICE_BY_ID",
    "list_languages",
    "list_voices",
    "public_voice",
    "get_voice",
    "clamp_speed",
    "synthesize_to_mp3",
]


def clamp_speed(speed: float) -> float:
    return max(0.8, min(1.2, float(speed)))


def estimate_speech_seconds(text: str, speed: float = 1.0) -> float:
    words = max(1, len(text.split()))
    seconds = (words / 150.0) * 60.0 / max(speed, 0.5)
    return max(1.5, min(seconds, 60.0))


def _espeak_binary() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _edge_rate(speed: float) -> str:
    speed = clamp_speed(speed)
    pct = int(round((speed - 1.0) * 100))
    if pct >= 0:
        return f"+{pct}%"
    return f"{pct}%"


def _resolve_edge_voice(voice_id: str) -> str:
    meta = get_voice(voice_id)
    if meta and meta.get("edge_voice"):
        return str(meta["edge_voice"])
    # Aura-only voice without edge mapping
    if meta and meta.get("deepgram_model"):
        raise RuntimeError(
            f"Voice {voice_id} requires Deepgram (no free Edge fallback mapped)"
        )
    return "en-US-AvaNeural"


def _resolve_espeak(voice_id: str) -> dict[str, str | int]:
    meta = get_voice(voice_id)
    if meta:
        pitch = 55 if meta.get("gender") == "female" else 35
        return {"voice": str(meta.get("espeak_voice") or "en"), "pitch": pitch}
    return {"voice": "en-us", "pitch": 50}


def _deepgram_model(voice_id: str) -> str | None:
    meta = get_voice(voice_id)
    if not meta:
        return None
    return meta.get("deepgram_model")


async def _edge_tts_async(
    text: str,
    out_path: Path,
    voice: str,
    speed: float = 1.0,
) -> int:
    import edge_tts

    edge_voice = _resolve_edge_voice(voice)
    rate = _edge_rate(speed)
    communicate = edge_tts.Communicate(
        text,
        edge_voice,
        rate=rate,
        boundary="WordBoundary",
    )

    audio_parts: list[bytes] = []
    words: list[dict] = []
    async for chunk in communicate.stream():
        kind = chunk.get("type")
        if kind == "audio":
            audio_parts.append(chunk["data"])
        elif kind in {"WordBoundary", "SentenceBoundary"}:
            start_s = float(chunk["offset"]) / 10_000_000.0
            dur_s = float(chunk["duration"]) / 10_000_000.0
            words.append(
                {
                    "text": str(chunk.get("text") or "").strip(),
                    "start_s": start_s,
                    "end_s": start_s + max(dur_s, 0.05),
                }
            )

    if not audio_parts:
        raise RuntimeError("edge-tts returned no audio")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(audio_parts)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(raw)
    try:
        run_ffmpeg(
            [
                "-i",
                str(tmp_path),
                "-af",
                "aformat=sample_fmts=s16:channel_layouts=mono:sample_rates=44100,volume=1.1,alimiter=limit=0.95:level=disabled",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out_path),
            ]
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    duration_ms = ffprobe_duration_ms(out_path)
    cues = group_words_into_cues(words)
    if not cues:
        cues = estimate_phrase_cues(text, duration_ms / 1000.0)
    write_cues(out_path, cues, provider="edge-tts")
    return duration_ms


def generate_edge_speech_mp3(
    text: str,
    out_path: Path,
    voice: str = "edge-en-ava",
    speed: float = 1.0,
) -> int:
    """Natural neural TTS via Microsoft Edge (free, multi-language)."""
    try:
        return asyncio.run(_edge_tts_async(text, out_path, voice, speed))
    except RuntimeError as e:
        if "asyncio.run()" in str(e) or "running event loop" in str(e).lower():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_edge_tts_async(text, out_path, voice, speed))
            finally:
                loop.close()
        raise


def generate_espeak_speech_mp3(
    text: str,
    out_path: Path,
    voice: str = "edge-en-ava",
    speed: float = 1.0,
) -> int:
    """Offline robotic fallback when network TTS is unavailable."""
    espeak = _espeak_binary()
    if not espeak:
        raise RuntimeError("espeak-ng not installed")

    speed = clamp_speed(speed)
    wpm = max(100, min(220, int(round(155 * speed))))
    cfg = _resolve_espeak(voice)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tts_mock_") as tmp:
        wav_path = Path(tmp) / "speech.wav"
        # Try language-specific voice, then plain language code, then English
        voice_candidates = [str(cfg["voice"]), str(cfg["voice"]).split("-")[0], "en"]
        last_err = "unknown"
        ok = False
        for vcode in voice_candidates:
            result = subprocess.run(
                [
                    espeak,
                    "-v",
                    vcode,
                    "-s",
                    str(wpm),
                    "-p",
                    str(cfg["pitch"]),
                    "-a",
                    "140",
                    "-g",
                    "6",
                    "-w",
                    str(wav_path),
                    "--",
                    text,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if result.returncode == 0 and wav_path.is_file() and wav_path.stat().st_size >= 44:
                ok = True
                break
            last_err = (result.stderr or result.stdout or "unknown error")[:500]
        if not ok:
            raise RuntimeError(f"espeak failed: {last_err}")

        run_ffmpeg(
            [
                "-i",
                str(wav_path),
                "-af",
                "aformat=sample_fmts=s16:channel_layouts=mono:sample_rates=44100,"
                "highpass=f=80,lowpass=f=8000,"
                "volume=1.4,"
                "alimiter=limit=0.89:level=disabled",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out_path),
            ]
        )
    duration_ms = ffprobe_duration_ms(out_path)
    write_cues(out_path, estimate_phrase_cues(text, duration_ms / 1000.0), provider="espeak")
    return duration_ms


def generate_tone_fallback_mp3(text: str, out_path: Path, speed: float = 1.0) -> int:
    duration = estimate_speech_seconds(text, speed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=523.25:duration={duration:.3f}",
            "-af",
            "volume=0.5",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(out_path),
        ]
    )
    try:
        duration_ms = ffprobe_duration_ms(out_path)
    except Exception:
        duration_ms = int(round(duration * 1000))
    write_cues(out_path, estimate_phrase_cues(text, duration_ms / 1000.0), provider="tone")
    return duration_ms


def generate_free_speech_mp3(
    text: str,
    out_path: Path,
    speed: float = 1.0,
    voice: str = "edge-en-ava",
) -> int:
    """Natural free multi-language TTS (Edge) with timed subtitle cues."""
    try:
        return generate_edge_speech_mp3(text, out_path, voice=voice, speed=speed)
    except Exception as e:
        logger.warning("edge-tts failed, falling back: %s", e)

    if _espeak_binary():
        try:
            return generate_espeak_speech_mp3(text, out_path, voice=voice, speed=speed)
        except Exception as e:
            logger.warning("espeak failed, using tone: %s", e)
    return generate_tone_fallback_mp3(text, out_path, speed)


def generate_deepgram_speech_mp3(
    text: str,
    out_path: Path,
    voice: str,
    speed: float = 1.0,
) -> int:
    settings = get_settings()
    model = _deepgram_model(voice)
    if not model:
        raise ValueError(f"Voice has no Deepgram model: {voice}")
    speed = clamp_speed(speed)
    params = {
        "model": model,
        "encoding": "mp3",
        "speed": str(speed),
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            settings.deepgram_base_url,
            params=params,
            headers=headers,
            json={"text": text},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Deepgram error {resp.status_code}: {resp.text[:500]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    duration_ms = ffprobe_duration_ms(out_path)
    write_cues(out_path, estimate_phrase_cues(text, duration_ms / 1000.0), provider="deepgram")
    return duration_ms


def synthesize_to_mp3(text: str, out_path: Path, voice: str, speed: float = 1.0) -> int:
    """
    Write MP3 + timed subtitle cues and return duration ms.

    Provider selection (per voice):
    1. Deepgram Aura-2 when API key is set and voice has a deepgram_model
       (selected Aura voices always try Deepgram when key is present)
    2. Free Edge neural voices (multi-language) — default / fallback
    """
    settings = get_settings()
    if not text.strip():
        raise ValueError("Narration text is empty")
    if voice not in VOICE_IDS:
        raise ValueError(f"Unsupported voice: {voice}")

    meta = get_voice(voice)
    # Selecting an Aura-2 voice + DEEPGRAM_API_KEY → use Deepgram (even if TTS_MOCK=true).
    # TTS_MOCK only affects default free path when no Deepgram key / non-Aura voices.
    has_deepgram = bool(settings.deepgram_api_key and _deepgram_model(voice))

    if has_deepgram:
        try:
            return generate_deepgram_speech_mp3(text, out_path, voice, speed)
        except Exception as e:
            logger.warning("Deepgram Aura TTS failed (%s); trying free Edge fallback", e)
            if not (meta and meta.get("edge_voice")):
                raise

    return generate_free_speech_mp3(text, out_path, speed=speed, voice=voice)
