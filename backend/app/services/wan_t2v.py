"""
Wan2.1 Text-to-Video 1.3B. Runs locally, with no ComfyUI process.

Backends (resolve_backend()):
  - diffusers: Hugging Face WanPipeline, model Wan-AI/Wan2.1-T2V-1.3B-Diffusers
  - cli:       official Wan2.1 generate.py --task t2v-1.3B
  - mock:      FFmpeg color clip ONLY when WAN_T2V_MOCK=true (not real AI video)

The 1.3B model is 480p (832×480 or 480×832). A ROCm PyTorch build reports the
GPU through torch.cuda, so this module never shells out to nvidia-smi.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import Settings, get_settings
from app.services.wan_i2v import _fit_duration
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

TASK = "t2v-1.3B"

_pipe_lock = threading.Lock()
_pipe = None
_pipe_model_id: str | None = None


@dataclass
class WanT2VResult:
    output_path: Path
    duration_ms: int
    backend: str
    cached: bool = False


def _frame_count(value: int) -> int:
    """Wan samples 4n+1 frames. The 1.3B checkpoint is trained around 81."""
    n = max(17, min(int(value), 81))
    return n - ((n - 1) % 4)


def choose_size(settings: Settings, frame_width: int | None = None, frame_height: int | None = None) -> tuple[int, int]:
    """1.3B supports 832×480 and 480×832. Portrait delivery uses the tall size."""
    if frame_width and frame_height and int(frame_height) > int(frame_width):
        return 480, 832
    width = int(settings.wan_t2v_width)
    height = int(settings.wan_t2v_height)
    if height > width:
        return 480, 832
    return 832, 480


def _gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _cli_script(settings: Settings) -> str:
    return (settings.wan_t2v_cli_script or settings.wan_i2v_cli_script or "").strip()


def _cli_python(settings: Settings) -> str:
    return (settings.wan_t2v_python or settings.wan_i2v_python or "python").strip() or "python"


def _cli_ready(settings: Settings) -> bool:
    ckpt = (settings.wan_t2v_ckpt_dir or "").strip()
    script = _cli_script(settings)
    return bool(ckpt and Path(ckpt).is_dir() and script and Path(script).is_file())


def resolve_backend() -> str:
    """Pick diffusers, the official CLI, or an explicit mock."""
    settings = get_settings()
    if not settings.wan_t2v_enabled:
        raise RuntimeError("Wan T2V is disabled (WAN_T2V_ENABLED=false)")

    requested = (settings.wan_t2v_backend or "auto").strip().lower()
    if settings.wan_t2v_mock or requested == "mock":
        return "mock"
    if requested in {"diffusers", "cli"}:
        return requested
    if requested != "auto":
        raise RuntimeError("WAN_T2V_BACKEND must be auto, diffusers, cli, or mock")

    if _gpu_available():
        return "diffusers"
    if _cli_ready(settings):
        return "cli"
    raise RuntimeError(
        "Wan2.1 T2V-1.3B runs on this machine, without ComfyUI. "
        "Install PyTorch (ROCm on the RX 9060 XT) and pip install -r requirements-wan.txt, "
        "or set WAN_T2V_CKPT_DIR to Wan2.1-T2V-1.3B and WAN_T2V_CLI_SCRIPT to generate.py. "
        "WAN_T2V_MOCK=true is an FFmpeg stand-in, not real video."
    )


def wan_t2v_status() -> dict:
    settings = get_settings()
    cuda = _gpu_available()
    torch_ok = False
    diffusers_ok = False
    try:
        import torch  # noqa: F401

        torch_ok = True
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
    except Exception as exc:
        backend = "unavailable"
        error = str(exc)

    real = backend in {"diffusers", "cli"}
    cli_ok = _cli_ready(settings)
    if backend == "diffusers":
        ready = diffusers_ok and (cuda or settings.wan_t2v_device == "cpu")
        if not ready and error is None:
            error = "Install torch and diffusers (requirements-wan.txt) on the render machine."
    elif backend == "cli":
        ready = cli_ok
        if not ready and error is None:
            error = "WAN_T2V_CKPT_DIR and WAN_T2V_CLI_SCRIPT must point at the official Wan2.1 checkout."
    else:
        ready = backend == "mock"

    return {
        "enabled": settings.wan_t2v_enabled,
        "backend": backend,
        "mock": backend == "mock",
        "real_ai": real and ready,
        "comfyui": False,
        "task": TASK,
        "model_id": settings.wan_t2v_model_id,
        "width": int(settings.wan_t2v_width),
        "height": int(settings.wan_t2v_height),
        "num_frames": _frame_count(settings.wan_t2v_num_frames),
        "guidance_scale": float(settings.wan_t2v_guidance_scale),
        "flow_shift": float(settings.wan_t2v_flow_shift),
        "torch_available": torch_ok,
        "diffusers_available": diffusers_ok,
        "cuda_available": cuda,
        "ckpt_dir": settings.wan_t2v_ckpt_dir or None,
        "cli_script": _cli_script(settings) or None,
        "ready": ready,
        "error": error,
        "hint": (
            None
            if real and ready
            else (
                "T2V-1.3B is local. Use Diffusers (WAN_T2V_BACKEND=diffusers) or the official "
                "generate.py --task t2v-1.3B. ComfyUI is not required."
            )
        ),
    }


def build_cli_command(settings: Settings, prompt: str, output_path: Path, *, width: int, height: int) -> list[str]:
    """Argument list for Wan2.1 generate.py. Does not start the process."""
    ckpt = (settings.wan_t2v_ckpt_dir or "").strip()
    script = _cli_script(settings)
    size = f"{width}*{height}"
    cmd = [
        _cli_python(settings),
        script,
        "--task",
        TASK,
        "--size",
        size,
        "--ckpt_dir",
        ckpt,
        "--frame_num",
        str(_frame_count(settings.wan_t2v_num_frames)),
        "--sample_steps",
        str(int(settings.wan_t2v_num_inference_steps)),
        "--sample_shift",
        str(float(settings.wan_t2v_flow_shift)),
        "--sample_guide_scale",
        str(float(settings.wan_t2v_guidance_scale)),
        "--prompt",
        prompt,
        "--save_file",
        str(output_path),
    ]
    if settings.wan_t2v_offload:
        cmd.extend(["--offload_model", "True", "--t5_cpu"])
    if settings.wan_t2v_seed >= 0:
        cmd.extend(["--base_seed", str(int(settings.wan_t2v_seed))])
    return cmd


def cache_key_for(
    prompt: str,
    *,
    backend: str,
    width: int,
    height: int,
    num_frames: int,
    guidance_scale: float,
    seed: int,
    steps: int,
) -> str:
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(
        f"{backend}|{width}x{height}|{num_frames}|{guidance_scale}|{seed}|{steps}|{TASK}".encode()
    )
    return h.hexdigest()[:32]


def unload_t2v() -> None:
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
        logger.info("Wan T2V unload skipped")


def generate_t2v(
    output_path: Path | str,
    prompt: str = "",
    *,
    negative_prompt: str | None = None,
    target_duration_s: float | None = None,
    cache_dir: Path | str | None = None,
    frame_width: int | None = None,
    frame_height: int | None = None,
    progress_cb: ProgressCb | None = None,
) -> WanT2VResult:
    """Generate a 480p clip from a text prompt. No input image and no ComfyUI."""
    settings = get_settings()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = (prompt or "").strip() or settings.wan_t2v_default_prompt
    neg = (
        (negative_prompt if negative_prompt is not None else settings.wan_t2v_negative_prompt)
        or DEFAULT_NEGATIVE_PROMPT
    )
    backend = resolve_backend()
    width, height = choose_size(settings, frame_width, frame_height)

    def progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)
        logger.info("wan_t2v[%s]: %s", backend, msg)

    key = cache_key_for(
        prompt,
        backend=backend,
        width=width,
        height=height,
        num_frames=_frame_count(settings.wan_t2v_num_frames),
        guidance_scale=float(settings.wan_t2v_guidance_scale),
        seed=int(settings.wan_t2v_seed),
        steps=int(settings.wan_t2v_num_inference_steps),
    )

    raw_out = output_path
    if cache_dir:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{backend}_{key}.mp4"
        if cached.is_file() and cached.stat().st_size > 0:
            progress("using cached Wan T2V clip")
            _fit_duration(cached, output_path, target_duration_s, settings.video_fps)
            return WanT2VResult(
                output_path=output_path,
                duration_ms=ffprobe_duration_ms(output_path),
                backend=f"{backend}+cache",
                cached=True,
            )
        raw_out = cached

    progress(f"generating with backend={backend}")
    if backend == "mock":
        progress("WARNING: mock mode — solid-color clip, not real Wan2.1 T2V")
        _generate_mock(raw_out, settings, width, height)
    elif backend == "diffusers":
        _generate_diffusers(raw_out, prompt, neg, settings, width, height, progress)
    elif backend == "cli":
        _generate_cli(raw_out, prompt, settings, width, height, progress)
    else:
        raise ValueError(f"Unknown wan_t2v backend: {backend}")

    if not raw_out.is_file() or raw_out.stat().st_size < 500:
        raise RuntimeError(f"Wan T2V produced no video file ({backend})")

    _fit_duration(raw_out, output_path, target_duration_s, settings.video_fps)
    return WanT2VResult(
        output_path=output_path,
        duration_ms=ffprobe_duration_ms(output_path),
        backend=backend,
        cached=False,
    )


def _generate_mock(output_path: Path, settings: Settings, width: int, height: int) -> None:
    fps = 16
    frames = _frame_count(settings.wan_t2v_num_frames)
    duration = frames / fps
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1a2744:s={width}x{height}:r={fps}:d={duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            str(output_path),
        ]
    )


def _inference_device(settings: Settings) -> str:
    requested = (settings.wan_t2v_device or "auto").strip().lower()
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        return "cuda"
    return "cuda" if _gpu_available() else "cpu"


def _generate_diffusers(
    output_path: Path,
    prompt: str,
    negative_prompt: str,
    settings: Settings,
    width: int,
    height: int,
    progress: ProgressCb,
) -> None:
    global _pipe, _pipe_model_id

    try:
        import torch
        from diffusers import AutoencoderKLWan, WanPipeline
        from diffusers.utils import export_to_video
    except ImportError as exc:
        raise RuntimeError(
            "Wan T2V diffusers backend requires torch, diffusers, and transformers. "
            "Install: pip install -r requirements-wan.txt"
        ) from exc

    model_id = settings.wan_t2v_model_id
    device = _inference_device(settings)
    if device == "cpu":
        logger.warning("Wan T2V-1.3B on CPU is extremely slow")

    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    frames = _frame_count(settings.wan_t2v_num_frames)

    with _pipe_lock:
        if _pipe is None or _pipe_model_id != model_id:
            progress(f"loading model {model_id}")
            vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
            pipe = WanPipeline.from_pretrained(model_id, vae=vae, torch_dtype=dtype)
            if settings.wan_t2v_offload and device == "cuda":
                pipe.enable_model_cpu_offload()
            else:
                pipe.to(device)
            _pipe = pipe
            _pipe_model_id = model_id
        pipe = _pipe

    shift = float(settings.wan_t2v_flow_shift)
    try:
        pipe.scheduler = pipe.scheduler.__class__.from_config(pipe.scheduler.config, flow_shift=shift)
    except Exception:
        logger.info("Wan T2V scheduler kept its default flow shift")

    generator = None
    if settings.wan_t2v_seed >= 0:
        # CPU generator stays valid when the pipeline offloads weights between steps.
        generator = torch.Generator(device="cpu").manual_seed(int(settings.wan_t2v_seed))

    progress(f"sampling {frames} frames @ {width}x{height}")
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        height=height,
        width=width,
        num_frames=frames,
        num_inference_steps=int(settings.wan_t2v_num_inference_steps),
        guidance_scale=float(settings.wan_t2v_guidance_scale),
        generator=generator,
    )
    progress("exporting video")
    export_to_video(result.frames[0], str(output_path), fps=16)


def _generate_cli(
    output_path: Path,
    prompt: str,
    settings: Settings,
    width: int,
    height: int,
    progress: ProgressCb,
) -> None:
    ckpt = (settings.wan_t2v_ckpt_dir or "").strip()
    script = _cli_script(settings)
    if not ckpt or not Path(ckpt).is_dir():
        raise RuntimeError("WAN_T2V_CKPT_DIR must point to downloaded Wan2.1-T2V-1.3B weights")
    if not script or not Path(script).is_file():
        raise RuntimeError("WAN_T2V_CLI_SCRIPT must point to Wan2.1 generate.py")

    cmd = build_cli_command(settings, prompt, output_path.resolve(), width=width, height=height)
    progress("running official Wan2.1 generate.py --task t2v-1.3B")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(script).parent),
        env=os.environ.copy(),
        timeout=settings.wan_t2v_timeout_s,
    )
    if result.returncode != 0 or not output_path.is_file():
        err = (result.stderr or result.stdout or "")[-3000:]
        raise RuntimeError(f"Wan2.1 T2V CLI failed ({result.returncode}): {err}")
