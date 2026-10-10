"""ComfyUI client for Qwen-Image-2.1 text-to-image.

The graph is the native API workflow: UNETLoader, CLIPLoader, VAELoader,
TextEncodeQwenImage21, EmptyLatentImage, KSampler, VAEDecode, SaveImage.
ComfyUI stays on port 8188. This client does not start vLLM.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable

logger = logging.getLogger(__name__)


def comfyui_is_local(settings: Settings) -> bool:
    host = (urlparse(settings.comfyui_base_url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def should_manage_comfyui(settings: Settings, *, injected_provider: bool) -> bool:
    """True when this image job should start ComfyUI and stop it when the job ends."""
    if injected_provider or not settings.comfyui_manage_process:
        return False
    return comfyui_is_local(settings)


def _comfy_dir(settings: Settings) -> Path:
    raw = (settings.comfyui_dir or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "ComfyUI"


def _comfy_python(settings: Settings) -> Path:
    raw = (settings.comfyui_python or "").strip()
    if raw:
        return Path(raw)
    return _comfy_dir(settings) / "venv" / "Scripts" / "python.exe"


def comfyui_is_up(settings: Settings) -> bool:
    url = settings.comfyui_base_url.rstrip("/") + "/system_stats"
    try:
        response = httpx.get(url, timeout=2)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def ensure_comfyui_server(settings: Settings) -> None:
    """Start the local ComfyUI process when Generate images needs it."""
    if comfyui_is_up(settings):
        return
    python = _comfy_python(settings)
    workdir = _comfy_dir(settings)
    if not python.is_file():
        raise ProviderUnavailable(
            f"ComfyUI Python was not found at {python}. Scene images need the local ComfyUI install."
        )
    parsed = urlparse(settings.comfyui_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8188
    log_dir = Path(__file__).resolve().parents[2] / "data" / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (log_dir / "comfy.err.log").open("a", encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("WAN_T2V_PRELOAD", None)
    env.pop("HSA_OVERRIDE_GFX_VERSION", None)
    logger.info("Starting ComfyUI at %s", settings.comfyui_base_url)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            [str(python), "main.py", "--listen", host, "--port", str(port)],
            cwd=str(workdir),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    finally:
        log_handle.close()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if comfyui_is_up(settings):
            return
        time.sleep(1)
    raise ProviderUnavailable("ComfyUI did not answer /system_stats within 180 seconds. See backend/data/run/comfy.err.log.")


def stop_comfyui_server() -> None:
    """Stop the local ComfyUI process so its GPU context is released."""
    _stop_python_matching("main.py", "8188")
    logger.info("Stopped ComfyUI so the GPU is free")


def _stop_python_matching(marker: str, port: str) -> None:
    if os.name != "nt":
        return
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*{0}*' -f '"
        + marker
        + "') -and $_.CommandLine -like ('*{0}*' -f '"
        + port
        + "') } | ForEach-Object { $_.ProcessId }"
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


REQUIRED_NODES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "TextEncodeQwenImage21",
    "EmptyLatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
)

# (object_info node, input name, Settings attribute, ComfyUI folder)
WEIGHT_INPUTS = (
    ("UNETLoader", "unet_name", "image_model", "models/diffusion_models"),
    ("CLIPLoader", "clip_name", "image_clip", "models/text_encoders"),
    ("VAELoader", "vae_name", "image_vae", "models/vae"),
)


class ImageGenerationError(RuntimeError):
    """ComfyUI accepted the call and then failed the prompt."""


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_config_path(value: str) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    candidate = backend_root() / value
    if candidate.is_file():
        return candidate
    return path


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ImageGenerationError(f"{path.name} is not a JSON object")
    return data


def set_mapped_value(graph: dict, path: str, value: Any) -> None:
    """Set a dotted path such as ``4.inputs.prompt``. Missing nodes are skipped."""
    node_id, _, rest = path.partition(".")
    if not rest or node_id not in graph:
        return
    cursor = graph[node_id]
    parts = rest.split(".")
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return
        cursor = cursor[part]
    if isinstance(cursor, dict):
        cursor[parts[-1]] = value


def combo_choices(info: dict, node: str, field: str) -> list[str] | None:
    """Return a loader's filename list, or None when this ComfyUI did not publish one."""
    spec = (((info.get(node) or {}).get("input") or {}).get("required") or {}).get(field)
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return [str(item) for item in spec[0]]
    return None


def missing_weight_files(info: dict, settings: Settings) -> list[str]:
    """Filenames the running ComfyUI cannot see. An absent combo list is not a miss."""
    missing: list[str] = []
    for node, field, attr, folder in WEIGHT_INPUTS:
        choices = combo_choices(info, node, field)
        if choices is None:
            continue
        filename = str(getattr(settings, attr, "") or "").strip()
        if filename and filename not in choices:
            missing.append(f"{folder}/{filename}")
    return missing


def format_comfy_error(path: str, status_code: int, payload: Any) -> str:
    """Turn a ComfyUI error body into one line. A bare status is the fallback."""
    details: list[str] = []
    if isinstance(payload, dict):
        node_errors = payload.get("node_errors") or {}
        if isinstance(node_errors, dict):
            for node in node_errors.values():
                errors = node.get("errors") if isinstance(node, dict) else None
                if not isinstance(errors, list):
                    continue
                for err in errors:
                    if not isinstance(err, dict):
                        continue
                    text = str(err.get("details") or err.get("message") or "").strip()
                    if text and text not in details:
                        details.append(text)
        error = payload.get("error")
        if not details and isinstance(error, dict):
            text = str(error.get("message") or "").strip()
            if text:
                details.append(text)
    suffix = "; ".join(details)
    if len(suffix) > 700:
        suffix = suffix[:700].rstrip() + "…"
    if suffix:
        return f"ComfyUI {path} failed ({status_code}): {suffix}"
    return f"ComfyUI {path} failed ({status_code})"


def qwen_canvas(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Fit the project frame under max_side and snap both sides to 32 pixels."""
    width = max(64, int(width))
    height = max(64, int(height))
    long_side = max(width, height)
    scale = min(1.0, max_side / long_side) if max_side > 0 else 1.0
    snapped_w = max(64, int(width * scale) // 32 * 32)
    snapped_h = max(64, int(height * scale) // 32 * 32)
    return snapped_w, snapped_h


def build_prompt_graph(
    settings: Settings,
    *,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    filename_prefix: str,
) -> dict:
    graph = copy.deepcopy(load_json(resolve_config_path(settings.image_workflow)))
    mapping = load_json(resolve_config_path(settings.image_workflow_map))
    values = {
        "checkpoint": settings.image_model,
        "clip": settings.image_clip,
        "vae": settings.image_vae,
        "positive": prompt,
        "negative": "",
        "resolution": max(int(width), int(height)),
        "seed": int(seed),
        "width": int(width),
        "height": int(height),
        "steps": int(settings.image_steps),
        "cfg": float(settings.image_cfg),
        "filename_prefix": filename_prefix,
    }
    for key, path in mapping.items():
        if key not in values or not isinstance(path, str):
            continue
        if key == "checkpoint" and not str(values[key] or "").strip():
            continue
        set_mapped_value(graph, path, values[key])
    return graph


class ComfyUIImageProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None, sleep=time.sleep) -> None:
        self.settings = settings
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(settings.comfyui_timeout_s, connect=10.0)
        )
        self._nodes_checked = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def ensure_nodes(self) -> None:
        if self._nodes_checked:
            return
        info = self._get("/object_info")
        if not isinstance(info, dict):
            raise ImageGenerationError("ComfyUI /object_info did not return node classes")
        missing = [name for name in REQUIRED_NODES if name not in info]
        if missing:
            raise ImageGenerationError(
                "ComfyUI is missing Qwen-Image-2.1 nodes: "
                + ", ".join(missing)
                + ". Update ComfyUI to 0.37 or newer and restart it."
            )
        weights = missing_weight_files(info, self.settings)
        if weights:
            raise ImageGenerationError(
                "ComfyUI is missing Qwen-Image-2.1 weights: "
                + ", ".join(weights)
                + ". Download them from https://huggingface.co/Comfy-Org/Qwen-Image-2.1 "
                + "into those folders under the ComfyUI models directory."
            )
        self._nodes_checked = True

    def generate(self, graph: dict, on_step=None) -> bytes:
        self.ensure_nodes()
        prompt_id = self.submit(graph)
        images = self.wait(prompt_id, on_step=on_step)
        if not images:
            raise ImageGenerationError("ComfyUI finished without an image")
        return self.download(images[0])

    def submit(self, graph: dict) -> str:
        payload = self._post("/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})
        if not isinstance(payload, dict):
            raise ImageGenerationError("ComfyUI /prompt returned an unexpected body")
        node_errors = payload.get("node_errors") or {}
        if node_errors:
            raise ImageGenerationError(f"ComfyUI node_errors: {node_errors}")
        error = payload.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ImageGenerationError(message or "ComfyUI rejected the prompt")
        prompt_id = payload.get("prompt_id")
        if not prompt_id:
            raise ImageGenerationError("ComfyUI did not return a prompt_id")
        return str(prompt_id)

    def wait(self, prompt_id: str, on_step=None) -> list[dict]:
        deadline = time.monotonic() + float(self.settings.comfyui_timeout_s)
        while time.monotonic() < deadline:
            payload = self._get(f"/history/{prompt_id}")
            entry = payload.get(prompt_id) if isinstance(payload, dict) else None
            if isinstance(entry, dict):
                status = str((entry.get("status") or {}).get("status_str") or "")
                if status == "error":
                    raise ImageGenerationError(f"ComfyUI prompt {prompt_id} failed")
                images = _history_images(entry)
                if images or status == "success":
                    return images
            if on_step:
                sample = self._sample_progress(prompt_id)
                if sample is not None:
                    on_step(*sample)
            self._sleep(self.settings.comfyui_poll_s)
        raise ImageGenerationError(f"ComfyUI prompt {prompt_id} timed out")

    def _sample_progress(self, prompt_id: str) -> tuple[int, int] | None:
        """ComfyUI /progress is optional. A missing route must not fail the image."""
        try:
            state = self._get("/progress")
        except Exception:
            return None
        if not isinstance(state, dict):
            return None
        nested = state.get("progress")
        if "max" not in state and isinstance(nested, dict):
            state = nested
        owner = str(state.get("prompt_id") or "")
        if owner and owner != prompt_id:
            return None
        try:
            value = int(state.get("value") or 0)
            maximum = int(state.get("max") or 0)
        except (TypeError, ValueError):
            return None
        if maximum <= 0:
            return None
        return value, maximum

    def download(self, image: dict) -> bytes:
        filename = str(image.get("filename") or "")
        subfolder = str(image.get("subfolder") or "")
        kind = str(image.get("type") or "output")
        if not filename:
            raise ImageGenerationError("ComfyUI image is missing a filename")
        url = self._url("/view")
        try:
            response = self._client.get(
                url,
                params={"filename": filename, "subfolder": subfolder, "type": kind},
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"ComfyUI is not reachable at {self.settings.comfyui_base_url}") from exc
        if response.status_code >= 400:
            raise ImageGenerationError(f"ComfyUI /view failed ({response.status_code})")
        if not response.content:
            raise ImageGenerationError("ComfyUI /view returned an empty image")
        return response.content

    def unload(self) -> None:
        """Best-effort. A stopped ComfyUI must not hide an image that already saved."""
        try:
            self._post("/free", {"unload_models": True, "free_memory": True})
        except Exception:
            logger.info("ComfyUI unload was skipped")

    def _post(self, path: str, body: dict) -> Any:
        return self._json("POST", path, json=body)

    def _get(self, path: str) -> Any:
        return self._json("GET", path)

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"ComfyUI is not reachable at {self.settings.comfyui_base_url}. Start it on port 8188."
            ) from exc
        if response.status_code >= 400:
            payload: Any = None
            try:
                payload = response.json()
            except Exception:
                payload = None
            raise ImageGenerationError(format_comfy_error(path, response.status_code, payload))
        try:
            return response.json()
        except Exception as exc:
            raise ImageGenerationError(f"ComfyUI {path} returned non-JSON") from exc

    def _url(self, path: str) -> str:
        return self.settings.comfyui_base_url.rstrip("/") + path


def _history_images(entry: dict) -> list[dict]:
    images: list[dict] = []
    outputs = entry.get("outputs") or {}
    if not isinstance(outputs, dict):
        return images
    for node in outputs.values():
        if isinstance(node, dict):
            found = node.get("images") or []
            if isinstance(found, list):
                images.extend(item for item in found if isinstance(item, dict))
    return images
