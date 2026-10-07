"""
Wan2.1 Image-to-Video generation service.

Backends (resolved by resolve_backend()):
  - fal:       fal.ai hosted Wan-2.1 I2V (recommended on Mac / no local GPU)
  - replicate: Replicate wavespeedai/wan-2.1-i2v-480p|720p
  - diffusers: local Hugging Face WanImageToVideoPipeline (CUDA)
  - cli:       official Wan2.1 generate.py + checkpoints
  - mock:      FFmpeg zoom stand-in ONLY when WAN_I2V_MOCK=true (not real AI video)

Official model: https://github.com/Wan-Video/Wan2.1
fal endpoint:  https://fal.ai/models/fal-ai/wan-i2v
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.utils.media import ffprobe_duration_ms, run_ffmpeg

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str], None]

DEFAULT_NEGATIVE_PROMPT = (
    "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, "
    "images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, "
    "incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, "
    "misshapen limbs, fused fingers, still picture, messy background, three legs, many people "
    "in the background, walking backwards"
)

_pipe_lock = threading.Lock()
_pipe = None
_pipe_model_id: str | None = None


def unload_i2v() -> None:
    """Drop the cached pipeline so the next GPU stage can load."""
    global _pipe, _pipe_model_id
    with _pipe_lock:
        _pipe = None
        _pipe_model_id = None
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        logger.info("Wan I2V unload skipped")


@dataclass
class WanI2VResult:
    output_path: Path
    duration_ms: int
    backend: str
    cached: bool = False


def resolve_backend() -> str:
    """Pick the actual inference backend from settings + available keys/GPU."""
    settings = get_settings()
    if not settings.wan_i2v_enabled:
        raise RuntimeError("Wan I2V is disabled (WAN_I2V_ENABLED=false)")

    requested = (settings.wan_i2v_backend or "auto").strip().lower()

    # Explicit mock only when user opts in
    if settings.wan_i2v_mock or requested == "mock":
        return "mock"

    if requested in {"fal", "replicate", "diffusers", "cli"}:
        return requested

    # auto: prefer cloud APIs (works on Mac/Docker without GPU), then local
    if settings.fal_key:
        return "fal"
    if settings.replicate_api_token:
        return "replicate"
    try:
        import torch

        if torch.cuda.is_available():
            return "diffusers"
    except Exception:
        pass
    if settings.wan_i2v_ckpt_dir and settings.wan_i2v_cli_script:
        return "cli"

    raise RuntimeError(
        "Real Wan2.1 image-to-video needs a cloud API key or a local GPU. "
        "Set FAL_KEY (https://fal.ai/models/fal-ai/wan-i2v) or REPLICATE_API_TOKEN, "
        "or set WAN_I2V_MOCK=true for the FFmpeg zoom stand-in (not real AI motion)."
    )


def wan_i2v_status() -> dict:
    """Health / capability snapshot for API and operators."""
    settings = get_settings()
    cuda = False
    torch_ok = False
    diffusers_ok = False
    try:
        import torch

        torch_ok = True
        cuda = bool(torch.cuda.is_available())
    except Exception:
        pass
    try:
        import diffusers  # noqa: F401

        diffusers_ok = True
    except Exception:
        pass

    error = None
    backend = None
    try:
        backend = resolve_backend()
    except Exception as e:
        backend = "unavailable"
        error = str(e)

    real = backend in {"fal", "replicate", "diffusers", "cli"}
    return {
        "enabled": settings.wan_i2v_enabled,
        "backend": backend,
        "mock": backend == "mock",
        "real_ai": real,
        "model_id": settings.wan_i2v_model_id,
        "resolution": settings.wan_i2v_resolution,
        "fal_configured": bool(settings.fal_key),
        "replicate_configured": bool(settings.replicate_api_token),
        "torch_available": torch_ok,
        "diffusers_available": diffusers_ok,
        "cuda_available": cuda,
        "ckpt_dir": settings.wan_i2v_ckpt_dir or None,
        "cli_script": settings.wan_i2v_cli_script or None,
        "ready": real or backend == "mock",
        "error": error,
        "hint": (
            None
            if real
            else (
                "Set FAL_KEY for real Wan2.1 I2V via fal.ai, or REPLICATE_API_TOKEN. "
                "Without a key, only mock zoom is available (WAN_I2V_MOCK=true)."
            )
        ),
    }


def cache_key_for(
    image_path: Path,
    prompt: str,
    *,
    backend: str,
    resolution: str,
    num_frames: int,
    guidance_scale: float,
    seed: int,
) -> str:
    h = hashlib.sha256()
    h.update(image_path.read_bytes())
    h.update(prompt.encode("utf-8"))
    h.update(f"{backend}|{resolution}|{num_frames}|{guidance_scale}|{seed}".encode())
    return h.hexdigest()[:32]


def generate_i2v(
    image_path: Path | str,
    output_path: Path | str,
    prompt: str = "",
    *,
    negative_prompt: str | None = None,
    target_duration_s: float | None = None,
    cache_dir: Path | str | None = None,
    progress_cb: ProgressCb | None = None,
) -> WanI2VResult:
    """
    Generate a motion video from a still image using Wan2.1 (or mock if opted in).

    Cache key includes backend so mock clips are never reused for real AI runs.
    """
    settings = get_settings()
    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not image_path.is_file():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    prompt = (prompt or "").strip() or settings.wan_i2v_default_prompt
    neg = (
        (negative_prompt if negative_prompt is not None else settings.wan_i2v_negative_prompt)
        or DEFAULT_NEGATIVE_PROMPT
    )
    backend = resolve_backend()

    def progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)
        logger.info("wan_i2v[%s]: %s", backend, msg)

    key = cache_key_for(
        image_path,
        prompt,
        backend=backend,
        resolution=settings.wan_i2v_resolution,
        num_frames=settings.wan_i2v_num_frames,
        guidance_scale=settings.wan_i2v_guidance_scale,
        seed=settings.wan_i2v_seed,
    )

    raw_out = output_path
    if cache_dir:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{backend}_{key}.mp4"
        if cached.is_file() and cached.stat().st_size > 0:
            progress("using cached Wan I2V clip")
            _fit_duration(cached, output_path, target_duration_s, settings.video_fps)
            return WanI2VResult(
                output_path=output_path,
                duration_ms=ffprobe_duration_ms(output_path),
                backend=f"{backend}+cache",
                cached=True,
            )
        raw_out = cached

    progress(f"generating with backend={backend}")
    if backend == "mock":
        progress("WARNING: mock mode — FFmpeg zoom only, not real Wan2.1 AI video")
        _generate_mock(image_path, raw_out, settings)
    elif backend == "fal":
        _generate_fal(image_path, raw_out, prompt, neg, settings, progress)
    elif backend == "replicate":
        _generate_replicate(image_path, raw_out, prompt, neg, settings, progress)
    elif backend == "diffusers":
        _generate_diffusers(image_path, raw_out, prompt, neg, settings, progress)
    elif backend == "cli":
        _generate_cli(image_path, raw_out, prompt, settings, progress)
    else:
        raise ValueError(f"Unknown wan_i2v backend: {backend}")

    if not raw_out.is_file() or raw_out.stat().st_size < 500:
        raise RuntimeError(f"Wan I2V produced no video file ({backend})")

    _fit_duration(raw_out, output_path, target_duration_s, settings.video_fps)
    return WanI2VResult(
        output_path=output_path,
        duration_ms=ffprobe_duration_ms(output_path),
        backend=backend,
        cached=False,
    )


# ---------------------------------------------------------------------------
# Cloud: fal.ai
# ---------------------------------------------------------------------------


def _image_data_uri(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        mime = "image/jpeg"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _generate_fal(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str,
    settings,
    progress: ProgressCb,
) -> None:
    """Call fal-ai/wan-i2v queue API (real Wan2.1 I2V)."""
    key = settings.fal_key
    if not key:
        raise RuntimeError("FAL_KEY is not set")

    endpoint = (settings.fal_wan_i2v_endpoint or "fal-ai/wan-i2v").strip().strip("/")
    resolution = "720p" if settings.wan_i2v_resolution == "720p" else "480p"
    num_frames = max(81, min(100, int(settings.wan_i2v_num_frames)))

    # Prefer data URI so local Docker images work without public URLs
    image_url = _image_data_uri(image_path)
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "image_url": image_url,
        "num_frames": num_frames,
        "frames_per_second": 16,
        "resolution": resolution,
        "num_inference_steps": int(settings.wan_i2v_num_inference_steps),
        "guide_scale": float(settings.wan_i2v_guidance_scale),
        "enable_safety_checker": False,
        "enable_prompt_expansion": bool(settings.wan_i2v_prompt_expansion),
        "acceleration": settings.wan_i2v_acceleration or "regular",
        "aspect_ratio": "auto",
    }
    if settings.wan_i2v_seed >= 0:
        payload["seed"] = int(settings.wan_i2v_seed)

    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    submit_url = f"https://queue.fal.run/{endpoint}"
    timeout = httpx.Timeout(60.0, read=120.0)
    progress("submitting to fal.ai Wan2.1 I2V…")

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.post(submit_url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"fal submit failed ({r.status_code}): {r.text[:1500]}")
        data = r.json()
        request_id = data.get("request_id") or data.get("requestId")
        status_url = data.get("status_url") or (
            f"https://queue.fal.run/{endpoint}/requests/{request_id}/status" if request_id else None
        )
        response_url = data.get("response_url") or (
            f"https://queue.fal.run/{endpoint}/requests/{request_id}" if request_id else None
        )
        if not status_url or not response_url:
            # Synchronous-style response with video already present
            video_url = _extract_video_url(data)
            if video_url:
                _download_file(client, video_url, output_path, headers=None)
                return
            raise RuntimeError(f"fal submit: missing queue URLs: {data}")

        progress(f"fal request_id={request_id}")
        deadline = time.time() + settings.wan_i2v_timeout_s
        while time.time() < deadline:
            sr = client.get(status_url, headers=headers)
            if sr.status_code >= 400:
                raise RuntimeError(f"fal status failed ({sr.status_code}): {sr.text[:1000]}")
            st = sr.json()
            status = (st.get("status") or "").upper()
            logs = st.get("logs") or []
            if logs:
                last = logs[-1]
                msg = last.get("message") if isinstance(last, dict) else str(last)
                if msg:
                    progress(f"fal: {msg[:120]}")
            if status in {"COMPLETED", "OK", "SUCCESS"}:
                break
            if status in {"FAILED", "ERROR", "CANCELLED"}:
                raise RuntimeError(f"fal generation failed: {st}")
            time.sleep(2.5)
        else:
            raise RuntimeError("fal Wan I2V timed out")

        rr = client.get(response_url, headers=headers)
        if rr.status_code >= 400:
            raise RuntimeError(f"fal result failed ({rr.status_code}): {rr.text[:1500]}")
        result = rr.json()
        video_url = _extract_video_url(result)
        if not video_url:
            raise RuntimeError(f"fal result missing video URL: {str(result)[:800]}")
        progress("downloading fal video…")
        _download_file(client, video_url, output_path, headers=None)


def _extract_video_url(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    # Nested under data (some clients)
    for root in (payload, payload.get("data") or {}, payload.get("output") or {}):
        if not isinstance(root, dict):
            continue
        video = root.get("video")
        if isinstance(video, dict) and video.get("url"):
            return str(video["url"])
        if isinstance(video, str) and video.startswith("http"):
            return video
        if root.get("video_url"):
            return str(root["video_url"])
        if root.get("url") and str(root["url"]).endswith((".mp4", ".webm")):
            return str(root["url"])
    return None


# ---------------------------------------------------------------------------
# Cloud: Replicate
# ---------------------------------------------------------------------------


def _generate_replicate(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str,
    settings,
    progress: ProgressCb,
) -> None:
    token = settings.replicate_api_token
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN is not set")

    model = settings.replicate_wan_model or (
        "wavespeedai/wan-2.1-i2v-720p"
        if settings.wan_i2v_resolution == "720p"
        else "wavespeedai/wan-2.1-i2v-480p"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    image_uri = _image_data_uri(image_path)
    # Replicate models typically accept image as URL or data URI
    inp = {
        "image": image_uri,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "num_frames": max(81, min(100, int(settings.wan_i2v_num_frames))),
        "frames_per_second": 16,
        "guidance_scale": float(settings.wan_i2v_guidance_scale),
        "num_inference_steps": int(settings.wan_i2v_num_inference_steps),
    }
    if settings.wan_i2v_seed >= 0:
        inp["seed"] = int(settings.wan_i2v_seed)

    create_url = "https://api.replicate.com/v1/models/" + model.strip("/") + "/predictions"
    progress(f"submitting to Replicate {model}…")

    with httpx.Client(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True) as client:
        r = client.post(create_url, headers=headers, json={"input": inp})
        if r.status_code >= 400:
            # Fallback to version-less predictions with model owner/name string
            r = client.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json={"version": None, "model": model, "input": inp},
            )
        if r.status_code >= 400:
            raise RuntimeError(f"Replicate submit failed ({r.status_code}): {r.text[:1500]}")
        pred = r.json()
        get_url = pred.get("urls", {}).get("get") or f"https://api.replicate.com/v1/predictions/{pred.get('id')}"
        deadline = time.time() + settings.wan_i2v_timeout_s
        while time.time() < deadline:
            status = (pred.get("status") or "").lower()
            progress(f"replicate: {status}")
            if status == "succeeded":
                break
            if status in {"failed", "canceled"}:
                raise RuntimeError(f"Replicate failed: {pred.get('error') or pred}")
            time.sleep(2.5)
            gr = client.get(get_url, headers={"Authorization": f"Bearer {token}"})
            if gr.status_code >= 400:
                raise RuntimeError(f"Replicate poll failed ({gr.status_code}): {gr.text[:800]}")
            pred = gr.json()
        else:
            raise RuntimeError("Replicate Wan I2V timed out")

        out = pred.get("output")
        video_url = None
        if isinstance(out, str):
            video_url = out
        elif isinstance(out, list) and out:
            video_url = out[-1] if isinstance(out[-1], str) else None
        elif isinstance(out, dict):
            video_url = out.get("url") or out.get("video")
        if not video_url:
            raise RuntimeError(f"Replicate missing output URL: {pred}")
        progress("downloading Replicate video…")
        _download_file(client, str(video_url), output_path, headers=None)


def _download_file(client: httpx.Client, url: str, dest: Path, headers: dict | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, headers=headers or {}) as resp:
        if resp.status_code >= 400:
            raise RuntimeError(f"download failed ({resp.status_code}) for {urlparse(url).netloc}")
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)


# ---------------------------------------------------------------------------
# Mock / local / CLI
# ---------------------------------------------------------------------------


def _generate_mock(image_path: Path, output_path: Path, settings) -> None:
    """FFmpeg zoom stand-in — NOT real Wan2.1. Only used when WAN_I2V_MOCK=true."""
    fps = 16
    frames = max(16, min(settings.wan_i2v_num_frames, 81))
    duration = frames / fps
    n = frames
    zoom_end = 1.12
    zoom_inc = (zoom_end - 1.0) / max(n - 1, 1)
    w, h = (832, 480) if settings.wan_i2v_resolution == "480p" else (1280, 720)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='min(1.0+on*{zoom_inc:.8f},{zoom_end})':"
        f"x='iw/2-(iw/zoom/2)+on*0.15':y='ih/2-(ih/zoom/2)':"
        f"d={n}:s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    run_ffmpeg(
        [
            "-loop",
            "1",
            "-i",
            str(image_path.resolve()),
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            str(output_path),
        ]
    )


def _generate_diffusers(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str,
    settings,
    progress: ProgressCb,
) -> None:
    global _pipe, _pipe_model_id

    try:
        import numpy as np
        import torch
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
        from diffusers.utils import export_to_video, load_image
        from transformers import CLIPVisionModel
    except ImportError as e:
        raise RuntimeError(
            "Wan I2V diffusers backend requires torch, diffusers, transformers. "
            "Install: pip install -r requirements-wan.txt — or use FAL_KEY instead."
        ) from e

    model_id = settings.wan_i2v_model_id
    device = settings.wan_i2v_device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        logger.warning("Wan I2V on CPU is extremely slow; use FAL_KEY or CUDA")

    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    with _pipe_lock:
        if _pipe is None or _pipe_model_id != model_id:
            progress(f"loading model {model_id}")
            image_encoder = CLIPVisionModel.from_pretrained(
                model_id, subfolder="image_encoder", torch_dtype=torch.float32
            )
            vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
            pipe = WanImageToVideoPipeline.from_pretrained(
                model_id,
                vae=vae,
                image_encoder=image_encoder,
                torch_dtype=dtype,
            )
            if settings.wan_i2v_offload and device == "cuda":
                try:
                    pipe.enable_model_cpu_offload()
                except Exception:
                    pipe.to(device)
            else:
                pipe.to(device)
            _pipe = pipe
            _pipe_model_id = model_id
        pipe = _pipe

    image = load_image(str(image_path))
    max_area = 720 * 1280 if settings.wan_i2v_resolution == "720p" else 480 * 832
    aspect_ratio = image.height / image.width
    mod_value = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
    height = round(np.sqrt(max_area * aspect_ratio)) // mod_value * mod_value
    width = round(np.sqrt(max_area / aspect_ratio)) // mod_value * mod_value
    height = max(mod_value, height)
    width = max(mod_value, width)
    image = image.resize((width, height))

    generator = None
    if settings.wan_i2v_seed >= 0:
        generator = torch.Generator(device=device if device != "cpu" else "cpu").manual_seed(
            settings.wan_i2v_seed
        )

    progress(f"sampling {settings.wan_i2v_num_frames} frames @ {width}x{height}")
    result = pipe(
        image=image,
        prompt=prompt,
        negative_prompt=negative_prompt,
        height=height,
        width=width,
        num_frames=settings.wan_i2v_num_frames,
        guidance_scale=settings.wan_i2v_guidance_scale,
        generator=generator,
    )
    frames = result.frames[0]
    progress("exporting video")
    export_to_video(frames, str(output_path), fps=16)


def _generate_cli(
    image_path: Path,
    output_path: Path,
    prompt: str,
    settings,
    progress: ProgressCb,
) -> None:
    ckpt = settings.wan_i2v_ckpt_dir
    script = settings.wan_i2v_cli_script
    if not ckpt or not Path(ckpt).is_dir():
        raise RuntimeError("WAN_I2V_CKPT_DIR must point to downloaded Wan2.1 I2V weights")
    if not script or not Path(script).is_file():
        raise RuntimeError("WAN_I2V_CLI_SCRIPT must point to Wan2.1 generate.py")

    size = "1280*720" if settings.wan_i2v_resolution == "720p" else "832*480"
    cmd = [
        settings.wan_i2v_python or "python",
        str(script),
        "--task",
        "i2v-14B",
        "--size",
        size,
        "--ckpt_dir",
        str(ckpt),
        "--image",
        str(image_path.resolve()),
        "--prompt",
        prompt,
        "--save_file",
        str(output_path.resolve()),
    ]
    if settings.wan_i2v_offload:
        cmd.extend(["--offload_model", "True", "--t5_cpu"])
    if settings.wan_i2v_seed >= 0:
        cmd.extend(["--base_seed", str(settings.wan_i2v_seed)])

    progress(f"running CLI: {' '.join(cmd[:8])}…")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(script).parent),
        env=os.environ.copy(),
        timeout=settings.wan_i2v_timeout_s,
    )
    if result.returncode != 0 or not output_path.is_file():
        err = (result.stderr or result.stdout or "")[-3000:]
        raise RuntimeError(f"Wan2.1 CLI failed ({result.returncode}): {err}")


def _fit_duration(
    src: Path,
    dst: Path,
    target_duration_s: float | None,
    fps: int,
) -> None:
    """Optionally loop/speed/trim to target duration. Temp file when src==dst."""
    src = Path(src)
    dst = Path(dst)
    same = src.resolve() == dst.resolve()

    if target_duration_s is None or target_duration_s <= 0:
        if not same:
            run_ffmpeg(
                [
                    "-i",
                    str(src.resolve()),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    str(dst),
                ]
            )
        return

    src_ms = ffprobe_duration_ms(src)
    src_s = max(0.05, src_ms / 1000.0)
    target = max(0.05, target_duration_s)

    if same and abs(src_s - target) <= 0.05:
        return

    out_target = dst
    tmp: Path | None = None
    if same:
        tmp = dst.with_suffix(dst.suffix + ".tmp.mp4")
        out_target = tmp

    if src_s + 0.05 < target:
        loops = int(target / src_s) + 1
        run_ffmpeg(
            [
                "-stream_loop",
                str(loops),
                "-i",
                str(src.resolve()),
                "-t",
                f"{target:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-r",
                str(fps),
                "-pix_fmt",
                "yuv420p",
                str(out_target),
            ]
        )
    elif src_s > target + 0.05:
        factor = src_s / target
        run_ffmpeg(
            [
                "-i",
                str(src.resolve()),
                "-filter:v",
                f"setpts=PTS/{factor:.6f}",
                "-t",
                f"{target:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-r",
                str(fps),
                "-pix_fmt",
                "yuv420p",
                str(out_target),
            ]
        )
    else:
        run_ffmpeg(
            [
                "-i",
                str(src.resolve()),
                "-t",
                f"{target:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-r",
                str(fps),
                "-pix_fmt",
                "yuv420p",
                str(out_target),
            ]
        )

    if tmp is not None and tmp.is_file():
        shutil.move(str(tmp), str(dst))
