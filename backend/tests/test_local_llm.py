import json

import httpx
import pytest

from app.config import Settings
from app.services.local_llm import LocalLLMProvider, configured_local_model, is_local_model, local_catalog_rows
from app.services.openrouter_llm import ProviderUnavailable
from app.services.story_job import build_llm_provider


def _settings() -> Settings:
    return Settings(
        local_llm_base_url="http://127.0.0.1:11434/v1",
        local_llm_model="local/qwen2.5:7b",
        local_llm_api_key="",
    )


def test_local_model_parses_json_and_unloads_ollama():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in {key.lower() for key in request.headers}
        body = json.loads(request.content.decode())
        assert body["model"] == "qwen2.5:7b"
        assert body["keep_alive"] == 0
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"title": "ok"}'}}]})

    provider = LocalLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan") == {
        "title": "ok"
    }


def test_local_schema_rejection_retries_without_temperature():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        if body["response_format"]["type"] == "json_schema" or "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "temperature and response_format json_schema failed"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"title": "ok"}'}}]})

    provider = LocalLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan") == {
        "title": "ok"
    }
    assert calls[1]["response_format"]["type"] == "json_object"
    assert "keep_alive" in calls[1]


def test_stopped_local_server_is_a_clear_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = LocalLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderUnavailable, match="not reachable"):
        provider.complete_json(system="sys", user="write", schema={}, schema_name="story_plan")


def test_catalog_lists_server_models_and_a_configured_model_while_down():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.2:3b"}]})

    settings = _settings()
    settings.local_llm_model = ""
    rows, up = local_catalog_rows(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert up
    assert {row["id"] for row in rows} == {"local/qwen2.5:7b", "local/llama3.2:3b"}
    assert all(row["provider"] == "local" for row in rows)

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    settings.local_llm_model = "qwen2.5:7b"
    rows, up = local_catalog_rows(settings, client=httpx.Client(transport=httpx.MockTransport(down)))
    assert not up
    assert rows == [{"id": "local/qwen2.5:7b", "name": "qwen2.5:7b", "provider": "local", "supports_json": True}]


def test_configured_local_model_is_the_story_default_id():
    settings = _settings()
    settings.local_llm_model = "qwen3:8b"
    assert configured_local_model(settings) == "local/qwen3:8b"
    settings.local_llm_model = ""
    assert configured_local_model(settings) == ""
    settings.local_llm_model = "local/../secret"
    assert configured_local_model(settings) == ""


def test_build_llm_provider_routes_local_ids():
    settings = _settings()
    provider = build_llm_provider(settings, "local/llama3.2:3b")
    assert isinstance(provider, LocalLLMProvider)
    assert provider.settings.local_llm_model == "local/llama3.2:3b"
    assert is_local_model("local/qwen2.5:7b")
    assert not is_local_model("gpt-5.4-mini")
    assert not is_local_model("local/../secret")
