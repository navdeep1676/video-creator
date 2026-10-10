"""Header monitor: GPU versus CPU work, and GPU counter parsing. No GPU required."""

from pathlib import Path

from app.services.activity import (
    merge_gpu_totals,
    render_uses_gpu,
    stage_job_item,
    story_uses_gpu,
    video_job_item,
    voice_item,
)
from app.services.host_stats import (
    choose_adapter,
    cpu_percent,
    display_name,
    is_gpu_resident,
    load_process_roles,
    parse_engine,
    parse_meminfo,
    parse_proc_stat,
    shown_on_gpu,
    summarize_gpu,
)


def test_story_writing_does_not_use_the_gpu():
    assert story_uses_gpu({"llm_model": "gpt-5.4-mini"}) is False
    assert story_uses_gpu({"llm_model": "local/qwen2.5:7b"}) is False
    running = stage_job_item(
        job_id="1",
        project_id="p",
        project_title="Lamp",
        stage="story",
        status="running",
        progress=0,
        detail="The model is writing the story",
        payload={"llm_model": "gpt-5.4-mini"},
    )
    assert running is not None
    assert running["on_gpu"] is False
    assert running["uses_gpu"] is False


def test_images_and_music_are_gpu_work_and_voice_is_not():
    images = stage_job_item(
        job_id="1",
        project_id="p",
        project_title="Lamp",
        stage="images",
        status="running",
        progress=40,
        detail="scene 2/10",
        payload={},
    )
    music = stage_job_item(
        job_id="2",
        project_id="p",
        project_title="Lamp",
        stage="music",
        status="running",
        progress=10,
        detail=None,
        payload={},
    )
    voice = voice_item("p", "Lamp", {"ready": 2, "processing": 1, "missing": 7})
    assert images["on_gpu"] is True
    assert images["label"] == "Scene images"
    assert music["on_gpu"] is True
    assert voice["on_gpu"] is False
    assert voice["uses_gpu"] is False
    assert voice["progress"] == 20
    assert voice["status"] == "running"
    assert voice_item("p", "Lamp", {"ready": 4}) is None


def test_wan_sampling_is_on_the_gpu_and_ffmpeg_is_not():
    assert render_uses_gpu("wan 1/2 step 3/50") is True
    assert render_uses_gpu("wan 1/1 cached") is False
    assert render_uses_gpu("mux") is False
    motion = video_job_item(
        job_id="1",
        project_id="p",
        project_title="Lamp",
        status="processing",
        progress=22,
        stage="wan 1/2 step 3/50",
    )
    encode = video_job_item(
        job_id="1",
        project_id="p",
        project_title="Lamp",
        status="processing",
        progress=80,
        stage="mux",
    )
    assert motion["on_gpu"] is True
    assert motion["status"] == "running"
    assert motion["href"].endswith("/export")
    assert encode["on_gpu"] is False
    assert encode["uses_gpu"] is False
    assert encode["label"] == "Export"


def test_gpu_summary_keeps_the_discrete_adapter_and_real_work():
    adapters = [
        {"luid": "aaa", "phys": 0, "dedicated": 0},
        {"luid": "bbb", "phys": 0, "dedicated": 12_000_000_000},
    ]
    assert choose_adapter(adapters, []) == ("bbb", 0)
    engines = [
        {"pid": 10, "luid": "bbb", "phys": 0, "util": 27.0},
        {"pid": 11, "luid": "aaa", "phys": 0, "util": 80.0},
    ]
    memory = [
        {"pid": 10, "luid": "bbb", "phys": 0, "dedicated": 8_000_000_000},
        {"pid": 12, "luid": "bbb", "phys": 0, "dedicated": 400_000_000},
        {"pid": 13, "luid": "bbb", "phys": 0, "dedicated": 700_000_000},
    ]
    summary = summarize_gpu(adapters, engines, memory, {10: "Ollama", 13: "ComfyUI"})
    assert summary["vram_used"] == 12_000_000_000
    assert summary["utilization"] == 27.0
    names = [row["name"] for row in summary["processes"]]
    assert names == ["Ollama", "ComfyUI"]
    assert shown_on_gpu("dwm") is False
    assert shown_on_gpu("Ollama") is True
    idle = summarize_gpu(adapters, [], memory, {10: "dwm", 12: "chrome", 13: "ComfyUI"})
    assert idle["utilization"] is None
    assert [row["name"] for row in idle["processes"]] == ["ComfyUI"]
    assert all(row["on_gpu"] for row in summary["processes"])
    assert is_gpu_resident(400_000_000, 0.3) is False
    assert parse_engine(
        r"pid_71600_luid_0x00000000_0x00016b6c_phys_0_eng_2_engtype_Compute 0"
    ) == (71600, "00016b6c", 0, "compute")


def test_cpu_and_memory_parsers_and_process_names(tmp_path: Path):
    assert parse_proc_stat("cpu 10 0 5 80 5 0 0 0") == (15, 100)
    assert cpu_percent((15, 100), (25, 200)) == 10.0
    assert cpu_percent(None, (25, 200)) is None
    ram = parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 400 kB\n")
    assert ram["used"] == 600 * 1024
    assert ram["percent"] == 60.0
    assert display_name(4, r"C:\tools\ComfyUI\python.exe", {}) == "ComfyUI"
    assert display_name(4, r"C:\ai\llama-server.exe", {}) == "Ollama"
    assert display_name(9, r"C:\Python\python.exe", {9: "Render worker"}) == "Render worker"
    role_file = tmp_path / "processes.json"
    role_file.write_text('{"render": 42, "tasks": 0, "other": 7}', encoding="utf-8")
    assert load_process_roles(role_file) == {42: "Render worker"}
    assert load_process_roles(tmp_path / "missing.json") == {}


def test_merge_prefers_live_vram_use_and_keeps_the_total():
    merged = merge_gpu_totals(
        {"available": True, "utilization": 27.0, "vram_used": 100},
        {"vram_used": 50, "vram_total": 16000, "utilization": 1, "temperature": 60},
    )
    assert merged["vram_used"] == 100
    assert merged["utilization"] == 27.0
    assert merged["vram_total"] == 16000
    assert merged["temperature"] == 60
    fallback = merge_gpu_totals(
        {"available": False, "utilization": None, "vram_used": None},
        {"vram_used": 50, "vram_total": 16000, "utilization": 4, "temperature": None},
    )
    assert fallback["available"] is True
    assert fallback["vram_used"] == 50
    assert fallback["utilization"] == 4
