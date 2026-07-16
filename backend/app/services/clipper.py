from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.services.storage import LocalStorage, get_storage
from app.utils.media import ffprobe_duration_ms, run_ffmpeg


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ClipFrame:
    id: str
    time_ms: int
    image_key: str
    selected: bool = True
    narration: str = ""


@dataclass
class ClipSession:
    id: str
    user_id: str
    filename: str
    video_key: str
    duration_ms: int
    created_at: str
    frames: list[ClipFrame] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "video_key": self.video_key,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            "frames": [asdict(f) for f in self.frames],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClipSession":
        frames = [ClipFrame(**f) for f in data.get("frames") or []]
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            filename=data["filename"],
            video_key=data["video_key"],
            duration_ms=int(data["duration_ms"]),
            created_at=data["created_at"],
            frames=frames,
        )


def _session_dir_key(user_id: str, session_id: str) -> str:
    return f"uploads/clipper/{user_id}/{session_id}"


def _meta_key(user_id: str, session_id: str) -> str:
    return f"{_session_dir_key(user_id, session_id)}/session.json"


def save_session(session: ClipSession, storage: LocalStorage | None = None) -> None:
    storage = storage or get_storage()
    key = _meta_key(session.user_id, session.id)
    storage.put_bytes(key, json.dumps(session.to_dict(), indent=2).encode("utf-8"))


def load_session(user_id: str, session_id: str, storage: LocalStorage | None = None) -> ClipSession | None:
    storage = storage or get_storage()
    key = _meta_key(user_id, session_id)
    if not storage.exists(key):
        return None
    data = json.loads(storage.get_bytes(key).decode("utf-8"))
    if data.get("user_id") != user_id:
        return None
    return ClipSession.from_dict(data)


def delete_session(user_id: str, session_id: str, storage: LocalStorage | None = None) -> None:
    storage = storage or get_storage()
    root = storage.absolute_path(_session_dir_key(user_id, session_id))
    if root.exists() and root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def create_session_from_upload(
    user_id: str,
    filename: str,
    data: bytes,
    ext: str,
    storage: LocalStorage | None = None,
) -> ClipSession:
    storage = storage or get_storage()
    session_id = str(uuid4())
    video_key = f"{_session_dir_key(user_id, session_id)}/source{ext}"
    storage.put_bytes(video_key, data)
    path = storage.absolute_path(video_key)
    try:
        duration_ms = ffprobe_duration_ms(path)
    except Exception as e:
        storage.delete(video_key)
        raise RuntimeError(f"Could not read video duration: {e}") from e

    settings = get_settings()
    if duration_ms / 1000 > settings.max_video_duration_s:
        storage.delete(video_key)
        raise ValueError(f"Video exceeds max duration of {settings.max_video_duration_s // 60} minutes")

    session = ClipSession(
        id=session_id,
        user_id=user_id,
        filename=filename,
        video_key=video_key,
        duration_ms=duration_ms,
        created_at=utcnow_iso(),
        frames=[],
    )
    save_session(session, storage)
    return session


def _extract_frame_at(video_path: Path, time_s: float, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # -ss before -i for fast seek; re-encode single jpeg
    run_ffmpeg(
        [
            "-ss",
            f"{max(0.0, time_s):.3f}",
            "-i",
            str(video_path.resolve()),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path.resolve()),
        ]
    )


def extract_frames(
    session: ClipSession,
    *,
    interval_s: float = 3.0,
    max_frames: int | None = None,
    timestamps_s: list[float] | None = None,
    storage: LocalStorage | None = None,
) -> ClipSession:
    """Extract still images from the session video into session.frames (replaces previous)."""
    storage = storage or get_storage()
    settings = get_settings()
    cap = min(max_frames or settings.max_clipper_frames, settings.max_clipper_frames)
    video_path = storage.absolute_path(session.video_key)
    if not video_path.is_file():
        raise FileNotFoundError("Source video missing")

    duration_s = session.duration_ms / 1000.0
    times: list[float] = []
    if timestamps_s:
        times = sorted({max(0.0, min(t, max(0.0, duration_s - 0.05))) for t in timestamps_s})
    else:
        interval_s = max(0.5, float(interval_s))
        # Start near 0.1s to avoid pure black first frames, then step
        t = min(0.1, duration_s / 2 if duration_s > 0 else 0)
        while t < duration_s and len(times) < cap:
            times.append(t)
            t += interval_s
        if not times and duration_s > 0:
            times = [0.0]

    times = times[:cap]

    # Clear old frames files
    frames_dir = storage.absolute_path(f"{_session_dir_key(session.user_id, session.id)}/frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    frames: list[ClipFrame] = []
    for i, t in enumerate(times):
        frame_id = str(uuid4())
        rel = f"{_session_dir_key(session.user_id, session.id)}/frames/{i:04d}_{frame_id[:8]}.jpg"
        out = storage.absolute_path(rel)
        _extract_frame_at(video_path, t, out)
        frames.append(
            ClipFrame(
                id=frame_id,
                time_ms=int(round(t * 1000)),
                image_key=rel,
                selected=True,
                narration="",
            )
        )

    session.frames = frames
    save_session(session, storage)
    return session


def update_frame_meta(
    session: ClipSession,
    frame_id: str,
    *,
    selected: bool | None = None,
    narration: str | None = None,
    storage: LocalStorage | None = None,
) -> ClipSession:
    storage = storage or get_storage()
    for f in session.frames:
        if f.id == frame_id:
            if selected is not None:
                f.selected = selected
            if narration is not None:
                f.narration = narration
            break
    else:
        raise KeyError("Frame not found")
    save_session(session, storage)
    return session


def bulk_update_frames(
    session: ClipSession,
    updates: list[dict],
    storage: LocalStorage | None = None,
) -> ClipSession:
    storage = storage or get_storage()
    by_id = {f.id: f for f in session.frames}
    for u in updates:
        fid = u.get("frame_id") or u.get("id")
        if not fid or fid not in by_id:
            continue
        f = by_id[fid]
        if "selected" in u and u["selected"] is not None:
            f.selected = bool(u["selected"])
        if "narration" in u and u["narration"] is not None:
            f.narration = str(u["narration"])
    save_session(session, storage)
    return session


def estimate_frame_count(duration_ms: int, interval_s: float, max_frames: int) -> int:
    if duration_ms <= 0:
        return 0
    interval_s = max(0.5, interval_s)
    n = math.ceil((duration_ms / 1000.0) / interval_s)
    return min(max(1, n), max_frames)
