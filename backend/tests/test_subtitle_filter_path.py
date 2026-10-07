from pathlib import Path

from app.services.ffmpeg_pipeline import escape_subtitles_filter_path


def test_drive_colon_is_escaped_twice_for_the_subtitles_filter(tmp_path: Path):
    ass = tmp_path / "job.ass"
    ass.write_text("x", encoding="utf-8")
    escaped = escape_subtitles_filter_path(ass)
    assert "\\\\:" in escaped
    assert escaped.replace("\\\\:", "").find(":") == -1
    assert escaped.endswith("/job.ass")
