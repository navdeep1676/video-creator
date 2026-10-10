"""CPU, RAM, and which processes are using the discrete GPU.

Windows reads CPU and RAM through kernel32 and GPU counters through PDH.
Those counters name each process, so the monitor can say who is on the GPU.
Linux reads /proc. A machine with neither source returns empty numbers.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Ignore the desktop and browsers. A real model load is hundreds of MB,
# and a sampling job shows up as a few percent on a compute engine.
VRAM_RESIDENT_BYTES = 512 * 1024 * 1024
UTIL_RESIDENT = 2.0
MAX_GPU_PROCESSES = 8

_ENGINE = re.compile(
    r"pid_(\d+)_luid_0x[0-9a-fA-F]+_0x([0-9a-fA-F]+)_phys_(\d+).*?engtype_([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_PROC_MEM = re.compile(
    r"pid_(\d+)_luid_0x[0-9a-fA-F]+_0x([0-9a-fA-F]+)_phys_(\d+)",
    re.IGNORECASE,
)
_ADAPTER = re.compile(
    r"luid_0x[0-9a-fA-F]+_0x([0-9a-fA-F]+)_phys_(\d+)",
    re.IGNORECASE,
)

# The Windows desktop always owns a slice of VRAM. It is not a Naratto job.
_HIDDEN_GPU_NAMES = {
    "dwm",
    "csrss",
    "explorer",
    "system",
    "registry",
    "smss",
    "wininit",
    "services",
    "lsass",
    "svchost",
    "fontdrvhost",
    "sihost",
    "ctfmon",
    "searchhost",
    "startmenuexperiencehost",
    "shellexperiencehost",
    "shellhost",
    "textinputhost",
    "widgetboard",
    "lockapp",
    "applicationframehost",
    "runtimebroker",
    "taskhostw",
    "dllhost",
    "conhost",
    "audiodg",
}

_ROLE_LABELS = {
    "render": "Render worker",
    "tasks": "Task worker",
    "api": "API",
    "frontend": "Vite",
    "beat": "Scheduler",
    "comfy": "ComfyUI",
    "ace": "ACE-Step",
    "ollama": "Ollama",
}

_cpu_lock = threading.Lock()
_cpu_prev: tuple[int, int] | None = None


def empty_meters() -> dict[str, Any]:
    return {
        "cpu": {"percent": None},
        "ram": {"used": None, "total": None, "percent": None},
        "gpu": {"available": False, "utilization": None, "vram_used": None},
        "processes": [],
    }


def parse_proc_stat(line: str) -> tuple[int, int] | None:
    """Return (busy, total) jiffies from a /proc/stat cpu line."""
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    try:
        nums = [int(part) for part in parts[1:]]
    except ValueError:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    return total - idle, total


def cpu_percent(previous: tuple[int, int] | None, current: tuple[int, int] | None) -> float | None:
    if previous is None or current is None:
        return None
    busy = current[0] - previous[0]
    total = current[1] - previous[1]
    if total <= 0:
        return None
    return round(max(0.0, min(100.0, 100.0 * busy / total)), 1)


def parse_meminfo(text: str) -> dict[str, int | float | None]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        token = rest.strip().split()[0] if rest.strip() else ""
        if token.isdigit():
            values[key] = int(token) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable", values.get("MemFree"))
    if total is None or available is None:
        return {"used": None, "total": total, "percent": None}
    used = max(0, total - available)
    percent = round(100.0 * used / total, 1) if total else None
    return {"used": used, "total": total, "percent": percent}


def parse_engine(name: str) -> tuple[int, str, int, str] | None:
    match = _ENGINE.search(name or "")
    if not match:
        return None
    return int(match.group(1)), match.group(2).lower(), int(match.group(3)), match.group(4).lower()


def parse_process_memory(name: str) -> tuple[int, str, int] | None:
    match = _PROC_MEM.search(name or "")
    if not match:
        return None
    return int(match.group(1)), match.group(2).lower(), int(match.group(3))


def parse_adapter(name: str) -> tuple[str, int] | None:
    match = _ADAPTER.search(name or "")
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def is_gpu_resident(vram_used: int, utilization: float) -> bool:
    return utilization >= UTIL_RESIDENT or vram_used >= VRAM_RESIDENT_BYTES


def choose_adapter(adapters: list[dict[str, Any]], engines: list[dict[str, Any]]) -> tuple[str, int] | None:
    """The discrete GPU is the adapter holding the most dedicated memory."""
    if adapters:
        best = max(adapters, key=lambda row: int(row.get("dedicated") or 0))
        if int(best.get("dedicated") or 0) > 0:
            return str(best["luid"]), int(best["phys"])
    totals: dict[tuple[str, int], float] = {}
    for row in engines:
        key = (str(row["luid"]), int(row["phys"]))
        totals[key] = totals.get(key, 0.0) + float(row.get("util") or 0)
    if not totals:
        return None
    return max(totals, key=lambda key: totals[key])


def summarize_gpu(
    adapters: list[dict[str, Any]],
    engines: list[dict[str, Any]],
    process_memory: list[dict[str, Any]],
    names: dict[int, str],
) -> dict[str, Any]:
    chosen = choose_adapter(adapters, engines)
    if chosen is None:
        return {"available": False, "utilization": None, "vram_used": None, "processes": []}
    luid, phys = chosen
    vram_used = None
    for row in adapters:
        if str(row["luid"]) == luid and int(row["phys"]) == phys:
            vram_used = int(row.get("dedicated") or 0)
            break
    per_pid_util: dict[int, float] = {}
    card_util = 0.0
    for row in engines:
        if str(row["luid"]) != luid or int(row["phys"]) != phys:
            continue
        util = float(row.get("util") or 0)
        card_util = max(card_util, util)
        pid = int(row["pid"])
        per_pid_util[pid] = max(per_pid_util.get(pid, 0.0), util)
    per_pid_vram: dict[int, int] = {}
    for row in process_memory:
        if str(row["luid"]) != luid or int(row["phys"]) != phys:
            continue
        pid = int(row["pid"])
        per_pid_vram[pid] = per_pid_vram.get(pid, 0) + int(row.get("dedicated") or 0)
    processes = []
    for pid in set(per_pid_util) | set(per_pid_vram):
        util = per_pid_util.get(pid, 0.0)
        vram = per_pid_vram.get(pid, 0)
        if not is_gpu_resident(vram, util):
            continue
        processes.append(
            {
                "pid": pid,
                "name": names.get(pid) or f"pid {pid}",
                "utilization": round(util, 1),
                "vram_used": vram,
                "on_gpu": True,
            }
        )
    processes = [row for row in processes if shown_on_gpu(str(row["name"]))]
    processes.sort(key=lambda row: (row["utilization"], row["vram_used"]), reverse=True)
    return {
        "available": True,
        "utilization": round(card_util, 1) if engines else None,
        "vram_used": vram_used,
        "processes": processes[:MAX_GPU_PROCESSES],
    }


def shown_on_gpu(name: str) -> bool:
    stem = Path(name).stem.lower()
    return stem not in _HIDDEN_GPU_NAMES


def display_name(pid: int, image: str | None, roles: dict[int, str]) -> str:
    if pid in roles:
        return roles[pid]
    if image:
        lowered = image.replace("\\", "/").lower()
        if "comfyui" in lowered or "/comfy" in lowered:
            return "ComfyUI"
        if "ace-step" in lowered or "acestep" in lowered:
            return "ACE-Step"
        if "ollama" in lowered or "llama-server" in lowered or "llama.cpp" in lowered:
            return "Ollama"
        stem = Path(image).stem
        if stem:
            return stem
    return f"pid {pid}"


def load_process_roles(path: Path) -> dict[int, str]:
    """Map launcher PIDs in processes.json to short names. Missing file is empty."""
    if not path.is_file():
        return {}
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    roles: dict[int, str] = {}
    for key, label in _ROLE_LABELS.items():
        try:
            pid = int(payload.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if pid > 0:
            roles[pid] = label
    return roles


def sample_host(roles: dict[int, str] | None = None) -> dict[str, Any]:
    """Best-effort meters. A failed probe leaves that section empty."""
    roles = roles or {}
    meters = empty_meters()
    try:
        cpu, ram = read_cpu_ram()
        meters["cpu"] = cpu
        meters["ram"] = ram
    except Exception:
        logger.exception("CPU and RAM sample failed")
    try:
        gpu = read_gpu(roles)
        meters["gpu"] = {key: gpu[key] for key in ("available", "utilization", "vram_used")}
        meters["processes"] = gpu.get("processes") or []
    except Exception:
        logger.exception("GPU sample failed")
    return meters


def read_cpu_ram() -> tuple[dict[str, Any], dict[str, Any]]:
    global _cpu_prev
    if os.name == "nt":
        ram = _windows_ram()
        ticks = _windows_cpu_ticks()
    else:
        stat = Path("/proc/stat")
        meminfo = Path("/proc/meminfo")
        if not stat.is_file() or not meminfo.is_file():
            return {"percent": None}, {"used": None, "total": None, "percent": None}
        ram = parse_meminfo(meminfo.read_text(encoding="utf-8", errors="replace"))
        ticks = parse_proc_stat(stat.read_text(encoding="utf-8", errors="replace").splitlines()[0])
    with _cpu_lock:
        percent = cpu_percent(_cpu_prev, ticks)
        _cpu_prev = ticks
    return {"percent": percent}, {
        "used": ram.get("used"),
        "total": ram.get("total"),
        "percent": ram.get("percent"),
    }


def read_gpu(roles: dict[int, str]) -> dict[str, Any]:
    if os.name == "nt":
        return _windows_gpu.sample(roles)
    return {"available": False, "utilization": None, "vram_used": None, "processes": []}


def _windows_ram() -> dict[str, int | float | None]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"used": None, "total": None, "percent": None}
    total = int(status.ullTotalPhys)
    used = max(0, total - int(status.ullAvailPhys))
    percent = round(100.0 * used / total, 1) if total else None
    return {"used": used, "total": total, "percent": percent}


def _filetime_int(value: Any) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def _windows_cpu_ticks() -> tuple[int, int] | None:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    if not ok:
        return None
    idle_i = _filetime_int(idle)
    kernel_i = _filetime_int(kernel)
    user_i = _filetime_int(user)
    # Kernel time includes idle time.
    total = kernel_i + user_i
    busy = (kernel_i - idle_i) + user_i
    return busy, total


class _WindowsGpu:
    """Keep one PDH query open. Utilization needs two samples, so the first read has none."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._query: Any = None
        self._counters: dict[str, Any] = {}
        self._primed = False
        self._failed = False
        self._logged = False

    def sample(self, roles: dict[int, str]) -> dict[str, Any]:
        empty = {"available": False, "utilization": None, "vram_used": None, "processes": []}
        if self._failed:
            return empty
        with self._lock:
            try:
                self._ensure()
                self._collect()
                allow_util = self._primed
                self._primed = True
                return self._read(roles, allow_util=allow_util)
            except Exception:
                if not self._logged:
                    logger.exception("GPU counters unavailable")
                    self._logged = True
                self._failed = True
                return empty

    def _ensure(self) -> None:
        if self._query is not None:
            return
        pdh = ctypes.WinDLL("pdh", use_last_error=True)
        pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhOpenQueryW.restype = wintypes.DWORD
        pdh.PdhAddEnglishCounterW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        pdh.PdhAddEnglishCounterW.restype = wintypes.DWORD
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhCollectQueryData.restype = wintypes.DWORD
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        pdh.PdhGetFormattedCounterArrayW.restype = wintypes.DWORD
        query = wintypes.HANDLE()
        status = pdh.PdhOpenQueryW(None, None, ctypes.byref(query))
        if status != 0:
            raise OSError(f"PdhOpenQueryW failed: {status:#x}")
        paths = {
            "adapter": r"\GPU Adapter Memory(*)\Dedicated Usage",
            "engine": r"\GPU Engine(*)\Utilization Percentage",
            "process": r"\GPU Process Memory(*)\Dedicated Usage",
        }
        counters: dict[str, Any] = {}
        for key, path in paths.items():
            handle = wintypes.HANDLE()
            added = pdh.PdhAddEnglishCounterW(query, path, None, ctypes.byref(handle))
            if added != 0:
                raise OSError(f"PdhAddEnglishCounterW {path} failed: {added:#x}")
            counters[key] = handle
        self._pdh = pdh
        self._query = query
        self._counters = counters

    def _collect(self) -> None:
        status = self._pdh.PdhCollectQueryData(self._query)
        if status != 0:
            raise OSError(f"PdhCollectQueryData failed: {status:#x}")

    def _read(self, roles: dict[int, str], *, allow_util: bool) -> dict[str, Any]:
        adapters = []
        for name, value in self._items("adapter", large=True):
            parsed = parse_adapter(name)
            if parsed is None:
                continue
            luid, phys = parsed
            adapters.append({"luid": luid, "phys": phys, "dedicated": max(0, int(value))})
        engines = []
        if allow_util:
            for name, value in self._items("engine", large=False):
                parsed = parse_engine(name)
                if parsed is None:
                    continue
                pid, luid, phys, _kind = parsed
                engines.append({"pid": pid, "luid": luid, "phys": phys, "util": max(0.0, float(value))})
        memory = []
        for name, value in self._items("process", large=True):
            parsed = parse_process_memory(name)
            if parsed is None:
                continue
            pid, luid, phys = parsed
            memory.append({"pid": pid, "luid": luid, "phys": phys, "dedicated": max(0, int(value))})
        pids = {int(row["pid"]) for row in engines} | {int(row["pid"]) for row in memory}
        exes = _process_exes()
        names = {
            pid: display_name(pid, _process_image(pid) or exes.get(pid), roles)
            for pid in pids
        }
        return summarize_gpu(adapters, engines, memory, names)

    def _items(self, key: str, *, large: bool) -> list[tuple[str, float]]:
        PDH_FMT_DOUBLE = 0x00000200
        PDH_FMT_LARGE = 0x00000400
        PDH_MORE_DATA = 0x800007D2
        fmt = PDH_FMT_LARGE if large else PDH_FMT_DOUBLE
        size = wintypes.DWORD(0)
        count = wintypes.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            self._counters[key], fmt, ctypes.byref(size), ctypes.byref(count), None
        )
        if status != PDH_MORE_DATA or size.value == 0:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        count = wintypes.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            self._counters[key], fmt, ctypes.byref(size), ctypes.byref(count), buffer
        )
        if status != 0 or count.value == 0:
            return []

        class _Value(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [
                    ("longValue", wintypes.LONG),
                    ("doubleValue", ctypes.c_double),
                    ("largeValue", ctypes.c_longlong),
                    ("AnsiStringValue", ctypes.c_char_p),
                    ("WideStringValue", ctypes.c_wchar_p),
                ]

            _anonymous_ = ("u",)
            _fields_ = [("CStatus", wintypes.DWORD), ("u", _U)]

        class _Item(ctypes.Structure):
            _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _Value)]

        array = ctypes.cast(buffer, ctypes.POINTER(_Item * count.value)).contents
        rows: list[tuple[str, float]] = []
        for item in array:
            # 0 is valid data. 1 is new data. Anything else is not a reading yet.
            if item.FmtValue.CStatus not in (0, 1):
                continue
            number = item.FmtValue.largeValue if large else item.FmtValue.doubleValue
            rows.append((str(item.szName or ""), float(number)))
        return rows


def _process_exes() -> dict[int, str]:
    """pid -> exe file name. Works for processes we cannot open."""
    if os.name != "nt":
        return {}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    names: dict[int, str] = {}
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            exe = str(entry.szExeFile or "").strip()
            if exe and entry.th32ProcessID:
                names[int(entry.th32ProcessID)] = exe
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def _process_image(pid: int) -> str | None:
    if pid <= 0:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value or None
    finally:
        kernel32.CloseHandle(handle)


_windows_gpu = _WindowsGpu()
