"""VRAM probe for AMD ROCm and ComfyUI."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

import httpx

from app.config import Settings


def empty_snapshot() -> dict[str, Any]:
    return {
        "available": False,
        "vram_total": None,
        "vram_used": None,
        "utilization": None,
        "temperature": None,
        "source": None,
    }


def snapshot(settings: Settings, timeout: float = 1.5) -> dict[str, Any]:
    result = empty_snapshot()
    comfy = _from_comfy(settings.comfyui_base_url, timeout)
    if comfy:
        result.update(comfy)
    rocm = _from_rocm()
    if rocm:
        for key in ("vram_total", "vram_used", "utilization", "temperature"):
            if result.get(key) is None and rocm.get(key) is not None:
                result[key] = rocm[key]
        if rocm.get("available"):
            result["available"] = True
        if result["source"] and rocm.get("source") and result["source"] != rocm["source"]:
            result["source"] = f"{result['source']}+{rocm['source']}"
        elif result["source"] is None:
            result["source"] = rocm.get("source")
    return result


def _from_comfy(base_url: str, timeout: float = 1.5) -> dict[str, Any] | None:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/system_stats", timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, OSError, ValueError):
        return None
    devices = body.get("devices") or []
    if not devices:
        return None
    device = devices[0]
    total = _as_int(device.get("vram_total"))
    free = _as_int(device.get("vram_free"))
    used = total - free if total is not None and free is not None else None
    return {
        "available": total is not None,
        "vram_total": total,
        "vram_used": used,
        "utilization": None,
        "temperature": None,
        "source": "comfyui",
    }


def _from_rocm() -> dict[str, Any] | None:
    if shutil.which("rocm-smi") is None:
        return None
    try:
        completed = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--showuse", "--showtemp", "--json"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    card = _first_card(payload)
    if card is None:
        return None
    total = used = utilization = temperature = None
    for key, value in card.items():
        lowered = key.lower()
        if "vram" in lowered and "total" in lowered and "used" not in lowered:
            total = _as_int(value)
        elif "vram" in lowered and "used" in lowered:
            used = _as_int(value)
        elif "gpu use" in lowered or lowered.endswith("use (%)"):
            utilization = _as_float(value)
        elif "temperature" in lowered and temperature is None:
            temperature = _as_float(value)
    if total is None and used is None and utilization is None and temperature is None:
        return None
    return {
        "available": total is not None or used is not None,
        "vram_total": total,
        "vram_used": used,
        "utilization": utilization,
        "temperature": temperature,
        "source": "rocm-smi",
    }


def _first_card(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for value in payload.values():
        if isinstance(value, dict):
            return value
    return payload


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().split()[0] if str(value).strip() else ""
    try:
        return float(text)
    except ValueError:
        return None
