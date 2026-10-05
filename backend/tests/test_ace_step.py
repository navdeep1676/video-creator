import json

import httpx
import pytest

from app.config import Settings
from app.services.ace_step import (
    AceStepMusicProvider,
    MusicGenerationError,
    generate_music_bytes,
    mark_music_failed,
    release_body,
)

WAV = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt "


def _settings() -> Settings:
    return Settings(
        acestep_base_url="http://acestep.test",
        comfyui_base_url="http://comfy.test",
        music_model="acestep-v15-turbo",
        acestep_thinking=False,
        acestep_timeout_s=2,
        acestep_poll_s=0,
    )


def _client(status: int, sink: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append((request.method, request.url.path, request.content))
        if request.url.path == "/free":
            return httpx.Response(200, json={})
        if request.url.path == "/release_task":
            return httpx.Response(200, json={"data": {"task_id": "task-1"}, "code": 200, "error": None})
        if request.url.path == "/query_result":
            result = json.dumps([{"file": "/v1/audio?path=track.wav", "status": 1}])
            if status == 2:
                result = "model exploded"
            return httpx.Response(
                200,
                json={
                    "data": [{"task_id": "task-1", "status": status, "result": result}],
                    "code": 200,
                    "error": None,
                },
            )
        if request.url.path == "/v1/audio":
            return httpx.Response(200, content=WAV)
        return httpx.Response(404, json={"detail": "missing"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _posted(sink: list) -> dict:
    for method, path, content in sink:
        if method == "POST" and path == "/release_task":
            return json.loads(content)
    raise AssertionError("ACE-Step was not called")


def test_request_includes_lyrics_and_audio_duration():
    sink: list = []
    settings = _settings()
    payload = {
        "content_type": "kids",
        "music_mode": "full_song",
        "music_prompt": "soft acoustic children's song",
        "lyrics": "[Verse]\nLittle lamp on the sill\n[Chorus]\nGlow glow home is still",
        "duration_seconds": 60,
        "language": "en",
    }
    provider = AceStepMusicProvider(settings, client=_client(1, sink), sleep=lambda _seconds: None)
    audio = provider.generate(release_body(payload, settings))
    body = _posted(sink)
    assert body["lyrics"] == payload["lyrics"]
    assert body["audio_duration"] == 60
    assert body["thinking"] is False
    assert body["batch_size"] == 1
    assert audio.startswith(b"RIFF")


def test_horror_background_is_instrumental():
    sink: list = []
    settings = _settings()
    payload = {
        "content_type": "horror",
        "music_mode": "background",
        "music_prompt": "low drones in an empty stairwell",
        "lyrics": "[Chorus]\nthis must not be sung",
        "duration_seconds": 140,
        "language": "hi",
    }
    provider = AceStepMusicProvider(settings, client=_client(1, sink), sleep=lambda _seconds: None)
    provider.generate(release_body(payload, settings))
    body = _posted(sink)
    assert body["lyrics"] == ""
    assert "instrumental" in body["prompt"]
    assert "no vocals" in body["prompt"]
    assert body["audio_duration"] == 140
    assert body["vocal_language"] == "en"


def test_status_2_fails_the_music_job():
    sink: list = []
    settings = _settings()
    provider = AceStepMusicProvider(settings, client=_client(2, sink), sleep=lambda _seconds: None)
    job = type("Job", (), {"status": "running", "error": None})()
    payload = {
        "content_type": "kids",
        "music_mode": "background",
        "music_prompt": "soft acoustic children's song",
        "lyrics": "[Verse]\nOriginal words",
        "duration_seconds": 30,
        "language": "en",
    }
    with pytest.raises(MusicGenerationError) as caught:
        generate_music_bytes(provider, payload, settings)
    mark_music_failed(job, caught.value)
    assert job.status == "failed"
    assert "status 2" in job.error


def test_music_mode_none_skips_the_server():
    class Exploding:
        def generate(self, body):
            raise AssertionError(body)

    audio = generate_music_bytes(Exploding(), {"music_mode": "none"}, _settings())
    assert audio is None
    assert release_body({"music_mode": "none", "lyrics": "keep", "duration_seconds": 30}, _settings()) is None


def test_comfyui_is_unloaded_before_release():
    sink: list = []
    settings = _settings()
    provider = AceStepMusicProvider(settings, client=_client(1, sink), sleep=lambda _seconds: None)
    provider.generate(release_body({"content_type": "horror", "music_mode": "background", "duration_seconds": 30}, settings))
    paths = [path for _method, path, _content in sink]
    assert paths.index("/free") < paths.index("/release_task")


def test_duration_is_clamped_to_server_range():
    settings = _settings()
    short = release_body({"music_mode": "background", "content_type": "horror", "duration_seconds": 5}, settings)
    long = release_body({"music_mode": "background", "content_type": "horror", "duration_seconds": 900}, settings)
    assert short is not None and short["audio_duration"] == 10
    assert long is not None and long["audio_duration"] == 600
