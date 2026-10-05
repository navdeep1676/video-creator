"""Wan2.1 I2V service — mock backend smoke tests (no GPU)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.services.wan_i2v import generate_i2v, resolve_backend, wan_i2v_status


def _write_test_image(path: Path, size: tuple[int, int] = (640, 360)) -> None:
    img = Image.new("RGB", size, color=(40, 120, 200))
    img.save(path, format="JPEG", quality=90)


def _clear_settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings


def test_wan_i2v_status_reports_mock(monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_I2V_MOCK="true", WAN_I2V_BACKEND="mock", FAL_KEY="")
    status = wan_i2v_status()
    assert status["enabled"] is True
    assert status["mock"] is True
    assert status["ready"] is True
    get_settings.cache_clear()


def test_resolve_backend_requires_key_when_not_mock(monkeypatch):
    get_settings = _clear_settings(
        monkeypatch,
        WAN_I2V_MOCK="false",
        WAN_I2V_BACKEND="auto",
        FAL_KEY="",
        REPLICATE_API_TOKEN="",
    )
    with pytest.raises(RuntimeError, match="FAL_KEY|REPLICATE"):
        resolve_backend()
    get_settings.cache_clear()


def test_resolve_backend_fal(monkeypatch):
    get_settings = _clear_settings(
        monkeypatch,
        WAN_I2V_MOCK="false",
        WAN_I2V_BACKEND="auto",
        FAL_KEY="test-key-not-real",
    )
    assert resolve_backend() == "fal"
    get_settings.cache_clear()


def test_generate_i2v_mock(tmp_path: Path, monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_I2V_MOCK="true", WAN_I2V_BACKEND="mock")

    src = tmp_path / "in.jpg"
    out = tmp_path / "out.mp4"
    _write_test_image(src)

    result = generate_i2v(
        src,
        out,
        prompt="Gentle camera push-in over the scene",
        target_duration_s=2.0,
    )
    assert result.backend == "mock"
    assert out.is_file()
    assert out.stat().st_size > 1000
    assert result.duration_ms >= 1500
    get_settings.cache_clear()


def test_generate_i2v_cache(tmp_path: Path, monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_I2V_MOCK="true", WAN_I2V_BACKEND="mock")

    src = tmp_path / "in.jpg"
    cache = tmp_path / "cache"
    out1 = tmp_path / "a.mp4"
    out2 = tmp_path / "b.mp4"
    _write_test_image(src)

    r1 = generate_i2v(src, out1, prompt="test motion", cache_dir=cache, target_duration_s=1.5)
    assert r1.cached is False
    r2 = generate_i2v(src, out2, prompt="test motion", cache_dir=cache, target_duration_s=1.5)
    assert r2.cached is True
    assert out2.is_file()
    get_settings.cache_clear()