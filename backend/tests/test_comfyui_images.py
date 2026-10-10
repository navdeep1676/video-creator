"""Qwen-Image-2.1 through a fake ComfyUI. These tests do not call a GPU."""

import io
import json
import uuid

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.db.models import Project, Slide, StoryScene
from app.services.comfyui import (
    REQUIRED_NODES,
    ComfyUIImageProvider,
    ImageGenerationError,
    build_prompt_graph,
    format_comfy_error,
    missing_weight_files,
    qwen_canvas,
)
from app.services.image_job import _draw_project
from app.services.storage import LocalStorage

OBJECT_INFO = {name: {} for name in REQUIRED_NODES}
IMAGE = {
    "filename": "Naratto_00001_.png",
    "subfolder": "Naratto",
    "type": "output",
}


def _settings() -> Settings:
    return Settings(
        comfyui_base_url="http://comfy.test",
        comfyui_timeout_s=5,
        comfyui_poll_s=0,
        image_steps=25,
        image_cfg=1.0,
        image_max_side=1024,
    )


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (18, 18, 24)).save(buf, format="PNG")
    return buf.getvalue()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _provider(handler) -> ComfyUIImageProvider:
    return ComfyUIImageProvider(_settings(), client=_client(handler), sleep=lambda _seconds: None)


def _success_handler(sink: list):
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append((request.method, request.url.path, request.content, dict(request.url.params)))
        if request.url.path == "/object_info":
            return httpx.Response(200, json=OBJECT_INFO)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "prompt-1", "node_errors": {}})
        if request.url.path == "/history/prompt-1":
            return httpx.Response(
                200,
                json={
                    "prompt-1": {
                        "status": {"status_str": "success"},
                        "outputs": {"8": {"images": [IMAGE]}},
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=_png())
        if request.url.path == "/free":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"detail": "missing"})

    return handler


def test_canvas_fits_16_by_9_under_the_long_side():
    assert qwen_canvas(1920, 1080, 1024) == (1024, 576)


def test_prompt_body_contains_patched_seed_and_text():
    settings = _settings()
    graph = build_prompt_graph(
        settings,
        prompt="a lantern in a dark hallway",
        seed=123456,
        width=1024,
        height=576,
        filename_prefix="Naratto/demo/000",
    )
    sink: list = []
    provider = _provider(_success_handler(sink))
    image = provider.generate(graph)
    posted = next(json.loads(content) for method, path, content, _params in sink if path == "/prompt")
    body = posted["prompt"]
    assert body["4"]["inputs"]["prompt"] == "a lantern in a dark hallway"
    assert body["6"]["inputs"]["seed"] == 123456
    assert body["5"]["inputs"]["width"] == 1024
    assert body["5"]["inputs"]["height"] == 576
    assert body["4"]["inputs"]["resolution"] == 1024
    assert body["1"]["inputs"]["unet_name"] == settings.image_model
    assert "image_1" not in body["4"]["inputs"]
    assert "images.image_1" not in body["4"]["inputs"]
    assert "9" not in body
    assert body["6"]["inputs"]["latent_image"] == ["5", 0]
    assert image.startswith(b"\x89PNG")


def test_reference_image_feeds_the_qwen_encoder():
    graph = build_prompt_graph(
        _settings(),
        prompt="the same hallway, now the door opens",
        seed=7,
        width=1024,
        height=576,
        filename_prefix="Naratto/demo/001",
        reference_image="naratto-ref-001.png",
    )
    assert graph["9"]["class_type"] == "LoadImage"
    assert graph["9"]["inputs"]["image"] == "naratto-ref-001.png"
    assert graph["4"]["inputs"]["images.image_1"] == ["9", 0]
    assert graph["4"]["inputs"]["vae"] == ["3", 0]
    assert graph["6"]["inputs"]["latent_image"] == ["4", 2]


def test_download_uses_filename_subfolder_and_type():
    sink: list = []
    provider = _provider(_success_handler(sink))
    provider.generate(build_prompt_graph(_settings(), prompt="room", seed=1, width=1024, height=576, filename_prefix="Naratto/x/000"))
    params = next(params for _method, path, _content, params in sink if path == "/view")
    assert params["filename"] == "Naratto_00001_.png"
    assert params["subfolder"] == "Naratto"
    assert params["type"] == "output"


def test_http_400_keeps_the_comfy_validation_detail():
    message = format_comfy_error(
        "/prompt",
        400,
        {
            "error": {"message": "Prompt outputs failed validation"},
            "node_errors": {
                "1": {
                    "errors": [
                        {
                            "message": "Value not in list",
                            "details": "unet_name: 'qwen_image_2.1_int8_convrot.safetensors' not in []",
                        }
                    ]
                }
            },
        },
    )
    assert "unet_name" in message
    assert "400" in message


def test_empty_model_lists_name_the_missing_weights():
    info = {
        "UNETLoader": {"input": {"required": {"unet_name": [[], {}]}}},
        "CLIPLoader": {"input": {"required": {"clip_name": [[], {}]}}},
        "VAELoader": {"input": {"required": {"vae_name": [["pixel_space"], {}]}}},
    }
    missing = missing_weight_files(info, _settings())
    assert "models/diffusion_models/qwen_image_2.1_int8_convrot.safetensors" in missing
    assert "models/text_encoders/qwen3vl_8b_int8_convrot.safetensors" in missing
    assert "models/vae/qwen_image_2.1_vae_bf16.safetensors" in missing

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            body = {name: {} for name in REQUIRED_NODES}
            body.update(info)
            return httpx.Response(200, json=body)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "should-not-post"})
        return httpx.Response(404, json={})

    provider = _provider(handler)
    with pytest.raises(ImageGenerationError, match="missing Qwen-Image-2.1 weights"):
        provider.generate({})


def test_node_errors_fail_the_prompt():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            return httpx.Response(200, json=OBJECT_INFO)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"node_errors": {"1": {"errors": ["missing unet"]}}})
        return httpx.Response(404, json={})

    provider = _provider(handler)
    with pytest.raises(ImageGenerationError, match="node_errors"):
        provider.generate({})


def test_failed_history_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            return httpx.Response(200, json=OBJECT_INFO)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "prompt-9"})
        if request.url.path == "/history/prompt-9":
            return httpx.Response(200, json={"prompt-9": {"status": {"status_str": "error"}, "outputs": {}}})
        return httpx.Response(404, json={})

    provider = _provider(handler)
    with pytest.raises(ImageGenerationError, match="failed"):
        provider.generate({})


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, slides, scenes):
        self.slides = slides
        self.scenes = scenes

    def scalars(self, statement):
        rows = self.scenes if "story_scenes" in str(statement) else self.slides
        return _Rows(rows)

    def commit(self):
        return None

    def rollback(self):
        return None

    def add(self, _obj):
        return None


def test_one_slide_failure_keeps_the_other_image(monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path)
    monkeypatch.setattr("app.services.image_job.get_storage", lambda: storage)
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        owner_id=uuid.uuid4(),
        title="hallway",
        settings={"aspect_ratio": "16:9"},
        storage_bytes=0,
    )
    kept = Slide(id=uuid.uuid4(), project_id=project_id, order_index=0, duration_ms=5000, image_keys=[])
    failed = Slide(id=uuid.uuid4(), project_id=project_id, order_index=1, duration_ms=5000, image_keys=[])
    scenes = [
        StoryScene(project_id=project_id, index=0, image_prompt="a quiet hallway"),
        StoryScene(project_id=project_id, index=1, image_prompt="boom door"),
    ]

    class _Provider:
        def generate(self, graph):
            if "boom" in graph["4"]["inputs"]["prompt"]:
                raise ImageGenerationError("ComfyUI prompt prompt-2 failed")
            return _png()

    errors = _draw_project(_Session([kept, failed], scenes), project, _settings(), _Provider(), False)
    assert kept.image_key
    assert storage.exists(kept.image_key)
    assert failed.image_key is None
    assert len(errors) == 1
    assert errors[0].startswith("Slide 2:")


def test_second_scene_uses_the_previous_image(monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path)
    monkeypatch.setattr("app.services.image_job.get_storage", lambda: storage)
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        owner_id=uuid.uuid4(),
        title="hallway",
        settings={"aspect_ratio": "16:9"},
        storage_bytes=0,
    )
    first = Slide(id=uuid.uuid4(), project_id=project_id, order_index=0, duration_ms=5000, image_keys=[])
    second = Slide(id=uuid.uuid4(), project_id=project_id, order_index=1, duration_ms=5000, image_keys=[])
    scenes = [
        StoryScene(project_id=project_id, index=0, image_prompt="a quiet hallway"),
        StoryScene(project_id=project_id, index=1, image_prompt="the door opens"),
    ]
    graphs: list[dict] = []
    uploads: list[tuple[str, bytes]] = []

    class _Provider:
        def upload_image(self, data: bytes, filename: str) -> str:
            uploads.append((filename, data))
            return filename

        def generate(self, graph):
            graphs.append(json.loads(json.dumps(graph)))
            return _png()

    errors = _draw_project(_Session([first, second], scenes), project, _settings(), _Provider(), False)
    assert errors == []
    assert len(uploads) == 1
    assert uploads[0][0] == "naratto-ref-001.png"
    assert uploads[0][1].startswith(b"\x89PNG")
    assert "image_1" not in graphs[0]["4"]["inputs"]
    assert "images.image_1" not in graphs[0]["4"]["inputs"]
    assert graphs[1]["4"]["inputs"]["images.image_1"] == ["9", 0]
    assert graphs[1]["9"]["inputs"]["image"] == "naratto-ref-001.png"
    assert graphs[1]["4"]["inputs"]["prompt"].startswith("Keep the same characters")
    assert "the door opens" in graphs[1]["4"]["inputs"]["prompt"]


def test_existing_still_is_the_reference_for_the_next_scene(monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path)
    monkeypatch.setattr("app.services.image_job.get_storage", lambda: storage)
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        owner_id=uuid.uuid4(),
        title="hallway",
        settings={"aspect_ratio": "16:9"},
        storage_bytes=0,
    )
    key = f"uploads/{project_id}/images/kept.png"
    storage.put_bytes(key, _png())
    kept = Slide(
        id=uuid.uuid4(),
        project_id=project_id,
        order_index=0,
        duration_ms=5000,
        image_key=key,
        image_keys=[{"key": key, "duration_ms": None}],
    )
    nxt = Slide(id=uuid.uuid4(), project_id=project_id, order_index=1, duration_ms=5000, image_keys=[])
    scenes = [
        StoryScene(project_id=project_id, index=0, image_prompt="a quiet hallway"),
        StoryScene(project_id=project_id, index=1, image_prompt="the door opens"),
    ]
    graphs: list[dict] = []

    class _Provider:
        def upload_image(self, data: bytes, filename: str) -> str:
            assert data == _png()
            return "kept-ref.png"

        def generate(self, graph):
            graphs.append(graph)
            return _png()

    errors = _draw_project(_Session([kept, nxt], scenes), project, _settings(), _Provider(), False)
    assert errors == []
    assert len(graphs) == 1
    assert graphs[0]["9"]["inputs"]["image"] == "kept-ref.png"
    assert kept.image_key == key


def test_upload_image_returns_the_input_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "naratto-ref-001.png", "subfolder": "refs", "type": "input"})
        return httpx.Response(404, json={})

    provider = _provider(handler)
    assert provider.upload_image(_png(), "naratto-ref-001.png") == "refs/naratto-ref-001.png"


def test_comfyui_starts_before_the_node_check(monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path)
    monkeypatch.setattr("app.services.image_job.get_storage", lambda: storage)
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        owner_id=uuid.uuid4(),
        title="hallway",
        settings={"aspect_ratio": "16:9"},
        storage_bytes=0,
    )
    slide = Slide(id=uuid.uuid4(), project_id=project_id, order_index=0, duration_ms=5000, image_keys=[])
    scenes = [StoryScene(project_id=project_id, index=0, image_prompt="a quiet hallway")]
    order: list[str] = []

    class _Provider:
        def ensure_nodes(self):
            order.append("nodes")

        def generate(self, graph):
            order.append("draw")
            return _png()

    errors = _draw_project(
        _Session([slide], scenes),
        project,
        _settings(),
        _Provider(),
        False,
        on_start=lambda: order.append("start"),
    )
    assert errors == []
    assert order == ["start", "nodes", "draw"]


def test_stop_skips_the_remaining_scenes(monkeypatch, tmp_path):
    storage = LocalStorage(tmp_path)
    monkeypatch.setattr("app.services.image_job.get_storage", lambda: storage)
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        owner_id=uuid.uuid4(),
        title="hallway",
        settings={"aspect_ratio": "16:9"},
        storage_bytes=0,
    )
    first = Slide(id=uuid.uuid4(), project_id=project_id, order_index=0, duration_ms=5000, image_keys=[])
    second = Slide(id=uuid.uuid4(), project_id=project_id, order_index=1, duration_ms=5000, image_keys=[])
    scenes = [
        StoryScene(project_id=project_id, index=0, image_prompt="a quiet hallway"),
        StoryScene(project_id=project_id, index=1, image_prompt="the door opens"),
    ]
    calls: list[str] = []

    class _Provider:
        def generate(self, graph):
            calls.append(graph["4"]["inputs"]["prompt"])
            return _png()

    errors = _draw_project(
        _Session([first, second], scenes),
        project,
        _settings(),
        _Provider(),
        False,
        stopped=lambda: len(calls) >= 1,
    )
    assert errors == []
    assert len(calls) == 1
    assert first.image_key
    assert second.image_key is None
