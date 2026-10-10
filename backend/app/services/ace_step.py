"""ACE-Step 1.5 client. The server is a separate process on port 8001.

Naratto stays on port 8000. Do not start ACE-Step from a story call.
On the RX 9060 XT the server must use ACESTEP_LM_BACKEND=pt and
ACESTEP_OFFLOAD_TO_CPU=true. The default vLLM backend is CUDA-only.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable

logger = logging.getLogger(__name__)

# docs/en/API.md lists en, zh, ja as examples and does not list hi.
_DOCUMENTED_VOCAL_LANGUAGES = {"en", "zh", "ja"}


class MusicGenerationError(RuntimeError):
    """ACE-Step accepted the call and then failed the task."""


def mark_music_failed(job: Any, exc: BaseException) -> None:
    if getattr(job, "status", None) == "cancelled":
        return
    job.status = "failed"
    job.error = str(exc)


def release_body(payload: dict, settings: Settings) -> dict | None:
    """JSON for POST /release_task. None means music_mode=none and the server is not called."""
    mode = str(payload.get("music_mode") or "background")
    if mode == "none":
        return None
    content_type = str(payload.get("content_type") or "horror")
    scenes = _scene_cues(payload.get("scenes"))
    prompt, lyrics = _style_and_lyrics(
        content_type,
        mode,
        str(payload.get("music_prompt") or ""),
        str(payload.get("lyrics") or ""),
    )
    if scenes:
        prompt = _with_scene_timeline(prompt, scenes, sung=bool(lyrics))
    thinking = bool(settings.acestep_thinking)
    return {
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": clamp_duration(_full_duration(payload.get("duration_seconds"), scenes)),
        "audio_format": "wav",
        "inference_steps": 8,
        "thinking": thinking,
        "use_cot_caption": thinking,
        "use_cot_language": thinking,
        "batch_size": 1,
        "model": settings.music_model or "acestep-v15-turbo",
        "vocal_language": vocal_language(str(payload.get("language") or "en")),
    }


def acestep_is_local(settings: Settings) -> bool:
    host = (urlparse(settings.acestep_base_url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def should_manage_acestep(settings: Settings, payload: dict, *, injected_provider: bool) -> bool:
    """True when this job should start the local server and stop it after the track."""
    if injected_provider or not settings.acestep_manage_process:
        return False
    if not acestep_is_local(settings):
        return False
    return release_body(payload, settings) is not None


def _install_dir(settings: Settings) -> Path:
    raw = (settings.acestep_dir or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "ACE-Step-1.5"


def _python_path(settings: Settings) -> Path:
    raw = (settings.acestep_python or "").strip()
    if raw:
        return Path(raw)
    return _install_dir(settings) / "venv_rocm" / "Scripts" / "python.exe"


def _server_endpoint(settings: Settings) -> tuple[str, int]:
    parsed = urlparse(settings.acestep_base_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 8001


def server_is_up(settings: Settings) -> bool:
    url = settings.acestep_base_url.rstrip("/") + "/health"
    try:
        response = httpx.get(url, timeout=2)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("WAN_T2V_PRELOAD", None)
    env.update(
        {
            "ACESTEP_LM_BACKEND": "pt",
            "ACESTEP_OFFLOAD_TO_CPU": "true",
            "ACESTEP_CONFIG_PATH": "acestep-v15-turbo",
            "ACESTEP_LM_MODEL_PATH": "acestep-5Hz-lm-0.6B",
            "ACESTEP_INIT_LLM": "false",
            "ACESTEP_NO_INIT": "true",
            "HSA_OVERRIDE_GFX_VERSION": "11.0.0",
            "MIOPEN_FIND_MODE": "FAST",
            "TORCH_COMPILE_BACKEND": "eager",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return env


def ensure_acestep_server(settings: Settings) -> None:
    """Start the local ACE-Step process when Generate music needs it."""
    if server_is_up(settings):
        return
    python = _python_path(settings)
    workdir = _install_dir(settings)
    if not python.is_file():
        raise MusicGenerationError(
            f"ACE-Step Python was not found at {python}. Install it with scripts\\setup-acestep-windows.bat."
        )
    host, port = _server_endpoint(settings)
    log_dir = Path(__file__).resolve().parents[2] / "data" / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (log_dir / "ace.err.log").open("a", encoding="utf-8")
    logger.info("Starting ACE-Step at %s", settings.acestep_base_url)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            [str(python), "-u", r"acestep\api_server.py", "--host", host, "--port", str(port)],
            cwd=str(workdir),
            env=_child_env(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    finally:
        log_handle.close()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if server_is_up(settings):
            return
        time.sleep(1)
    raise MusicGenerationError("ACE-Step did not answer /health within 120 seconds. See backend/data/run/ace.err.log.")


def stop_acestep_server() -> None:
    """Stop the local API process so its GPU context is released."""
    if os.name != "nt":
        return
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*{0}*' -f 'api_server.py') "
        "-and $_.CommandLine -like ('*{0}*' -f 'acestep') } | "
        "ForEach-Object { $_.ProcessId }"
    )
    listed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    pids = [line.strip() for line in listed.stdout.splitlines() if line.strip().isdigit()]
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, check=False)
    if pids:
        logger.info("Stopped ACE-Step so the GPU is free")


def generate_music_bytes(provider: Any, payload: dict, settings: Settings, on_tick=None) -> bytes | None:
    body = release_body(payload, settings)
    if body is None:
        return None
    generate = provider.generate
    try:
        accepts_tick = "on_tick" in inspect.signature(generate).parameters
    except (TypeError, ValueError):
        accepts_tick = False
    if accepts_tick and on_tick is not None:
        return generate(body, on_tick=on_tick)
    return generate(body)


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


def ace_step_percent(item: dict) -> int | None:
    """Read a 0–100 percent from an ACE-Step query row, when the server sends one."""
    if not isinstance(item, dict):
        return None
    for key in ("progress", "progress_percent", "percentage"):
        raw = item.get(key)
        if raw is None or isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 1:
            value *= 100
        if 0 <= value <= 100:
            return int(round(value))
    return None


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
    """Horror background is instrumental. Kids and full_song sing the complete lyrics."""
    style = music_prompt.strip()
    sing = music_mode == "full_song" or content_type == "kids"
    if not sing:
        if not style:
            if content_type == "horror":
                style = "dark ambient horror score, low drones, dissonant strings"
            else:
                style = "cinematic original score"
        lowered = style.lower()
        if "instrumental" not in lowered and "no vocal" not in lowered:
            style = f"{style}, instrumental, no vocals"
        return style, ""
    if not style:
        if content_type == "kids":
            style = "gentle original children's song, acoustic guitar, soft tempo"
        elif content_type == "horror":
            style = "dark cinematic theme, low strings, slow tempo"
        else:
            style = "cinematic original score"
    return style, lyrics.strip()


def _scene_cues(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    cues = []
    for item in value:
        if isinstance(item, dict):
            cues.append(item)
    return cues


def _full_duration(value: Any, scenes: list[dict]) -> Any:
    """Cover the chosen length and every scene. Short requests stay short for clamping."""
    if not scenes:
        return value
    try:
        chosen = float(value)
    except (TypeError, ValueError):
        chosen = 0.0
    covered = 0.0
    for scene in scenes:
        try:
            covered += float(scene.get("duration") or 0)
        except (TypeError, ValueError):
            pass
        try:
            covered = max(covered, float(scene.get("end_time") or 0))
        except (TypeError, ValueError):
            pass
    if chosen <= 0 and covered <= 0:
        return value
    return max(chosen, covered)


def _with_scene_timeline(style: str, scenes: list[dict], *, sung: bool) -> str:
    if sung:
        lead = (
            "Full song for the entire duration. Sing the complete lyrics while the "
            "arrangement follows every scene in order."
        )
    else:
        lead = "Full instrumental score for the entire duration, following every scene in order."
    lines = [_scene_line(number, scene) for number, scene in enumerate(scenes, start=1)]
    return f"{style}. {lead} " + " ".join(lines)


def _scene_line(number: int, scene: dict) -> str:
    beat = str(scene.get("beat") or "scene").strip() or "scene"
    start = _clock(scene.get("start_time"))
    end = _clock(scene.get("end_time"))
    when = f"{start}-{end}" if start and end else ""
    cue = str(scene.get("music_prompt") or "").strip()
    if not cue:
        location = str(scene.get("location") or "").strip()
        narration = " ".join(str(scene.get("narration") or "").split())[:120]
        cue = ", ".join(part for part in (location, narration) if part) or beat
    else:
        cue = " ".join(cue.split())[:240]
    clock = f"{when}, " if when else ""
    return f"Scene {number} ({clock}{beat}): {cue}."


def _clock(value: Any) -> str:
    try:
        seconds = max(0.0, float(value))
    except (TypeError, ValueError):
        return ""
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def ensure_wav(data: bytes, ffmpeg: str = "ffmpeg") -> bytes:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data
    from app.utils.media import tool_path

    program = ffmpeg
    if not program or program == "ffmpeg" or not Path(program).is_file():
        program = tool_path("ffmpeg")
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

    def generate(self, body: dict, on_tick=None) -> bytes:
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
            if on_tick:
                on_tick(item)
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
