from pathlib import Path

import pytest

from app.utils import media


def test_tool_path_uses_a_configured_file(tmp_path: Path):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"")
    assert media.tool_path("ffmpeg", str(exe)) == str(exe)


def test_missing_ffmpeg_names_the_setting(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _name: None)
    monkeypatch.setattr(media, "_winget_tool", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="FFMPEG_PATH"):
        media.tool_path("ffmpeg", "ffmpeg")
