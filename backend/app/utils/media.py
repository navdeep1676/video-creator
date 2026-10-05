from __future__ import annotations

import json
import subprocess
from pathlib import Path


def ffprobe_duration_ms(path: Path | str) -> int:
    """Return media duration in milliseconds via ffprobe."""
    path = Path(path)
    cmd = [
        "ffprobe",
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
        ["ffmpeg", "-hide_banner", "-filters"],
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
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        stderr = result.stderr or ""
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {tail}")
