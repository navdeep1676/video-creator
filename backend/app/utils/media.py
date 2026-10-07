from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def tool_path(name: str, configured: str | None = None) -> str:
    """Find ffmpeg or ffprobe. A bare name is not a file path."""
    if configured is None:
        configured = _configured_tool(name)
    configured = (configured or "").strip().strip('"')
    bare = {name, f"{name}.exe"}
    if configured and configured.lower() not in bare:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(configured)
        if found:
            return found
        if any(sep in configured for sep in ("/", "\\")):
            setting = "FFMPEG_PATH" if name == "ffmpeg" else "FFPROBE_PATH"
            raise FileNotFoundError(f"{setting} does not point to {name}: {configured}")
    found = shutil.which(name)
    if found:
        return found
    discovered = _winget_tool(name)
    if discovered:
        return discovered
    setting = "FFMPEG_PATH" if name == "ffmpeg" else "FFPROBE_PATH" if name == "ffprobe" else f"{name.upper()}_PATH"
    raise FileNotFoundError(
        f"{name} was not found. Install FFmpeg, or set {setting} to the full path of {name}.exe."
    )


def _configured_tool(name: str) -> str:
    from app.config import get_settings

    settings = get_settings()
    if name == "ffprobe":
        return settings.ffprobe_path
    return settings.ffmpeg_path


def _winget_tool(name: str) -> str | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not root.is_dir():
        return None
    matches = sorted(root.glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"))
    if not matches:
        return None
    return str(matches[-1])


def ffprobe_duration_ms(path: Path | str) -> int:
    """Return media duration in milliseconds via ffprobe."""
    path = Path(path)
    cmd = [
        tool_path("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:500]}")
    data = json.loads(result.stdout)
    seconds = float(data["format"]["duration"])
    return int(round(seconds * 1000))


def ffmpeg_supports_subtitles() -> bool:
    """Homebrew's default ffmpeg bottle has no libass, so the subtitles filter is absent."""
    result = subprocess.run(
        [tool_path("ffmpeg"), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "subtitles":
            return True
    return False


def run_ffmpeg(args: list[str], timeout: int | None = None) -> None:
    cmd = [tool_path("ffmpeg"), "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        stderr = result.stderr or ""
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {tail}")
