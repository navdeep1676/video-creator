"""Wan2.1 T2V-1.3B — local Diffusers/CLI selection and mock clips. No GPU."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.wan_t2v import (
    build_cli_command,
    choose_size,
    generate_t2v,
    resolve_backend,
    wan_t2v_status,
)


def _clear_settings(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings


def test_status_reports_mock(monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_T2V_MOCK="true", WAN_T2V_BACKEND="mock")
    status = wan_t2v_status()
    assert status["enabled"] is True
    assert status["mock"] is True
    assert status["ready"] is True
    assert status["comfyui"] is False
    assert status["task"] == "t2v-1.3B"
    assert status["model_id"] == "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    get_settings.cache_clear()


def test_resolve_backend_requires_local_runtime(monkeypatch):
    get_settings = _clear_settings(
        monkeypatch,
        WAN_T2V_MOCK="false",
        WAN_T2V_BACKEND="auto",
        WAN_T2V_CKPT_DIR="",
        WAN_T2V_CLI_SCRIPT="",
        WAN_I2V_CLI_SCRIPT="",
    )
    monkeypatch.setattr("app.services.wan_t2v._gpu_available", lambda: False)
    with pytest.raises(RuntimeError, match="without ComfyUI"):
        resolve_backend()
    get_settings.cache_clear()


def test_resolve_backend_diffusers_is_explicit(monkeypatch):
    get_settings = _clear_settings(
        monkeypatch,
        WAN_T2V_MOCK="false",
        WAN_T2V_BACKEND="diffusers",
    )
    assert resolve_backend() == "diffusers"
    get_settings.cache_clear()


def test_resolve_backend_cli_when_weights_exist(monkeypatch, tmp_path: Path):
    ckpt = tmp_path / "Wan2.1-T2V-1.3B"
    ckpt.mkdir()
    script = tmp_path / "generate.py"
    script.write_text("# official entry\n", encoding="utf-8")
    get_settings = _clear_settings(
        monkeypatch,
        WAN_T2V_MOCK="false",
        WAN_T2V_BACKEND="auto",
        WAN_T2V_CKPT_DIR=str(ckpt),
        WAN_T2V_CLI_SCRIPT=str(script),
    )
    monkeypatch.setattr("app.services.wan_t2v._gpu_available", lambda: False)
    assert resolve_backend() == "cli"
    get_settings.cache_clear()


def test_cli_command_is_t2v_1_3b(monkeypatch, tmp_path: Path):
    get_settings = _clear_settings(
        monkeypatch,
        WAN_T2V_CKPT_DIR=str(tmp_path),
        WAN_T2V_CLI_SCRIPT=str(tmp_path / "generate.py"),
        WAN_T2V_GUIDANCE_SCALE="6",
        WAN_T2V_FLOW_SHIFT="8",
        WAN_T2V_NUM_FRAMES="81",
        WAN_T2V_OFFLOAD="true",
        WAN_T2V_SEED="7",
    )
    settings = get_settings()
    cmd = build_cli_command(settings, "a fox in snow", tmp_path / "out.mp4", width=832, height=480)
    assert "--task" in cmd
    assert cmd[cmd.index("--task") + 1] == "t2v-1.3B"
    assert cmd[cmd.index("--size") + 1] == "832*480"
    assert cmd[cmd.index("--sample_shift") + 1] == "8.0"
    assert cmd[cmd.index("--sample_guide_scale") + 1] == "6.0"
    assert cmd[cmd.index("--frame_num") + 1] == "81"
    assert "--t5_cpu" in cmd
    assert "comfy" not in " ".join(cmd).lower()
    get_settings.cache_clear()


def test_portrait_frame_uses_tall_size(monkeypatch):
    get_settings = _clear_settings(monkeypatch)
    settings = get_settings()
    assert choose_size(settings, 1920, 1080) == (832, 480)
    assert choose_size(settings, 1080, 1920) == (480, 832)
    get_settings.cache_clear()


def test_generate_t2v_mock(tmp_path: Path, monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_T2V_MOCK="true", WAN_T2V_BACKEND="mock")
    out = tmp_path / "out.mp4"
    result = generate_t2v(out, prompt="A lantern sways in fog", target_duration_s=2.0)
    assert result.backend == "mock"
    assert out.is_file()
    assert out.stat().st_size > 1000
    assert result.duration_ms >= 1500
    get_settings.cache_clear()


def test_generate_t2v_cache(tmp_path: Path, monkeypatch):
    get_settings = _clear_settings(monkeypatch, WAN_T2V_MOCK="true", WAN_T2V_BACKEND="mock")
    cache = tmp_path / "cache"
    out1 = tmp_path / "a.mp4"
    out2 = tmp_path / "b.mp4"
    first = generate_t2v(out1, prompt="same prompt", cache_dir=cache, target_duration_s=1.5)
    second = generate_t2v(out2, prompt="same prompt", cache_dir=cache, target_duration_s=1.5)
    assert first.cached is False
    assert second.cached is True
    assert out2.is_file()
    get_settings.cache_clear()
