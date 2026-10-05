"""ACE-Step 1.5 client. The server is a separate process on port 8001.

Naratto stays on port 8000. Do not start ACE-Step from a story call.
On the RX 9060 XT the server must use ACESTEP_LM_BACKEND=pt and
ACESTEP_OFFLOAD_TO_CPU=true. The default vLLM backend is CUDA-only.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable

logger = logging.getLogger(__name__)

# docs/en/API.md lists en, zh, ja as examples and does not list hi.
_DOCUMENTED_VOCAL_LANGUAGES = {"en", "zh", "ja"}


class MusicGenerationError(RuntimeError):
    """ACE-Step accepted the call and then failed the task."""


def mark_music_failed(job: Any, exc: BaseException) -> None:
    job.status = "failed"
    job.error = str(exc)


def release_body(payload: dict, settings: Settings) -> dict | None:
    """JSON for POST /release_task. None means music_mode=none and the server is not called."""
    mode = str(payload.get("music_mode") or "background")
    if mode == "none":
        return None
    content_type = str(payload.get("content_type") or "horror")
    prompt, lyrics = _style_and_lyrics(
        content_type,
        mode,
        str(payload.get("music_prompt") or ""),
        str(payload.get("lyrics") or ""),
    )
    thinking = bool(settings.acestep_thinking)
    return {
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": clamp_duration(payload.get("duration_seconds")),
        "audio_format": "wav",
        "inference_steps": 8,
        "thinking": thinking,
        "use_cot_caption": thinking,
        "use_cot_language": thinking,
        "batch_size": 1,
        "model": settings.music_model or "acestep-v15-turbo",
        "vocal_language": vocal_language(str(payload.get("language") or "en")),
    }


def generate_music_bytes(provider: Any, payload: dict, settings: Settings) -> bytes | None:
    body = release_body(payload, settings)
    if body is None:
        return None
    return provider.generate(body)


def clamp_duration(value: Any) -> int | float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 30.0
    if seconds < 10:
        seconds = 10.0
    if seconds > 600:
        seconds = 600.0
    if seconds.is_integer():
        return int(seconds)
    return seconds


def _status_code(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def vocal_language(language: str) -> str:
    code = (language or "en").strip().lower()
    if code in _DOCUMENTED_VOCAL_LANGUAGES:
        return code
    return "en"


def _style_and_lyrics(content_type: str, music_mode: str, music_prompt: str, lyrics: str) -> tuple[str, str]:
    style = music_prompt.strip()
    if content_type == "horror" and music_mode == "background":
        if not style:
            style = "dark ambient horror score, low drones, dissonant strings"
        lowered = style.lower()
        if "instrumental" not in lowered and "no vocal" not in lowered:
            style = f"{style}, instrumental, no vocals"
        return style, ""
    if not style:
        if content_type == "kids":
            style = "gentle original children's song, acoustic guitar, soft tempo"
        else:
            style = "cinematic original score"
    sung = lyrics.strip() if music_mode == "full_song" or content_type == "kids" else ""
    return style, sung


def ensure_wav(data: bytes, ffmpeg: str = "ffmpeg") -> bytes:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data
    program = shutil.which(ffmpeg) or ffmpeg
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "source.bin"
        target = folder / "background.wav"
        source.write_bytes(data)
        completed = subprocess.run(
            [program, "-y", "-i", str(source), str(target)],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0 or not target.is_file():
            raise MusicGenerationError("ACE-Step audio was not wav and FFmpeg could not transcode it")
        return target.read_bytes()


class AceStepMusicProvider:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        sleep=None,
    ):
        self.settings = settings
        self._client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._sleep = sleep or time.sleep

    def generate(self, body: dict) -> bytes:
        self.unload_comfyui()
        created = self._send(
            "POST",
            self._url("/release_task"),
            json=body,
            headers=self._headers(),
        )
        task_id = self._task_id(created)
        deadline = time.monotonic() + max(1.0, float(self.settings.acestep_timeout_s))
        while True:
            polled = self._send(
                "POST",
                self._url("/query_result"),
                json={"task_id_list": [task_id]},
                headers=self._headers(),
            )
            item = self._query_item(polled, task_id)
            status = _status_code(item.get("status"))
            if status == 1:
                return ensure_wav(self._download(self._file_url(item)))
            if status == 2:
                detail = item.get("result") or item.get("error") or ""
                message = "ACE-Step generation failed (status 2)"
                if detail:
                    message = f"{message}: {detail}"
                raise MusicGenerationError(message)
            if time.monotonic() >= deadline:
                raise MusicGenerationError("ACE-Step timed out before the track was ready")
            self._sleep(float(self.settings.acestep_poll_s))

    def unload_comfyui(self) -> None:
        """Best-effort. A stopped ComfyUI must not block the music request."""
        url = self.settings.comfyui_base_url.rstrip("/") + "/free"
        try:
            self._client.request(
                "POST",
                url,
                json={"unload_models": True, "free_memory": True},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
        except Exception:
            logger.info("ComfyUI unload skipped before ACE-Step")

    def _task_id(self, response: httpx.Response) -> str:
        data = self._data(response)
        if isinstance(data, dict) and data.get("task_id"):
            return str(data["task_id"])
        raise MusicGenerationError("ACE-Step did not return a task_id")

    def _query_item(self, response: httpx.Response, task_id: str) -> dict:
        data = self._data(response)
        rows = data if isinstance(data, list) else []
        for row in rows:
            if isinstance(row, dict) and str(row.get("task_id") or task_id) == task_id:
                return row
        if rows and isinstance(rows[0], dict):
            return rows[0]
        raise MusicGenerationError("ACE-Step query returned no task")

    def _file_url(self, item: dict) -> str:
        result = item.get("result")
        if isinstance(result, str):
            result = json.loads(result)
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list) or not result:
            raise MusicGenerationError("ACE-Step result had no audio file")
        first = result[0]
        if isinstance(first, str):
            first = json.loads(first)
        file_url = first.get("file") if isinstance(first, dict) else None
        if not file_url:
            raise MusicGenerationError("ACE-Step result had no audio file")
        return str(file_url)

    def _download(self, file_url: str) -> bytes:
        if file_url.startswith("http://") or file_url.startswith("https://"):
            url = file_url
        else:
            url = urljoin(self.settings.acestep_base_url.rstrip("/") + "/", file_url.lstrip("/"))
        response = self._send("GET", url, headers=self._auth_header())
        if response.status_code >= 400:
            raise MusicGenerationError(f"ACE-Step audio download failed ({response.status_code})")
        if not response.content:
            raise MusicGenerationError("ACE-Step audio download was empty")
        return response.content

    def _data(self, response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise ProviderUnavailable("ACE-Step rejected ACESTEP_API_KEY")
        try:
            payload = response.json()
        except Exception as exc:
            raise MusicGenerationError(f"ACE-Step returned non-JSON ({response.status_code})") from exc
        if not isinstance(payload, dict):
            return payload
        code = payload.get("code")
        if response.status_code >= 400 or (code is not None and code != 200):
            message = payload.get("error") or payload.get("detail") or response.text
            raise MusicGenerationError(str(message))
        return payload.get("data")

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"ACE-Step is not reachable at {self.settings.acestep_base_url}. Start it on port 8001."
            ) from exc

    def _url(self, path: str) -> str:
        return self.settings.acestep_base_url.rstrip("/") + path

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self._auth_header())
        return headers

    def _auth_header(self) -> dict[str, str]:
        key = (self.settings.acestep_api_key or "").strip()
        if not key:
            return {}
        return {"Authorization": f"Bearer {key}"}
