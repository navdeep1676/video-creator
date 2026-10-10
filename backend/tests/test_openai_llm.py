import json

import httpx
import pytest

from app.config import Settings
from app.services.openai_llm import OpenAILLMProvider, is_openai_model, openai_catalog_rows
from app.services.openrouter_llm import ProviderUnavailable
from app.services.story_job import build_llm_provider


def _settings() -> Settings:
    return Settings(
        openai_api_key="sk-test",
        openai_model="gpt-5.4-mini",
        openrouter_api_key="or-key",
        openrouter_model="openrouter/free",
    )


def test_openai_parses_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-test"
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content.decode())
        assert body["model"] == "gpt-5.4-mini"
        assert body["response_format"]["type"] == "json_schema"
        assert body["temperature"] == 0.7
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"title": "ok"}'}}]})

    provider = OpenAILLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan") == {
        "title": "ok"
    }


def test_schema_and_temperature_rejection_retries_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        if body["response_format"]["type"] == "json_schema" or "temperature" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "temperature is unsupported and response_format json_schema failed"}},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"title": "ok"}'}}]})

    provider = OpenAILLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan") == {
        "title": "ok"
    }
    assert calls[1]["response_format"]["type"] == "json_object"
    assert "temperature" not in calls[1]
    assert "JSON schema" in calls[1]["messages"][0]["content"]


def test_missing_openai_key_does_not_call_the_api():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("chat should not be called without a key")

    settings = _settings()
    settings.openai_api_key = ""
    provider = OpenAILLMProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderUnavailable, match="OPENAI_API_KEY"):
        provider.complete_json(system="sys", user="write", schema={}, schema_name="story_plan")


def test_build_llm_provider_routes_openai():
    settings = _settings()
    provider = build_llm_provider(settings, "gpt-4.1-mini")
    assert isinstance(provider, OpenAILLMProvider)
    assert provider.settings.openai_model == "gpt-4.1-mini"
    assert not isinstance(build_llm_provider(settings, "openrouter/free"), OpenAILLMProvider)
    assert not isinstance(build_llm_provider(settings, "gemini-3.5-flash"), OpenAILLMProvider)
    with pytest.raises(ProviderUnavailable, match="Local story models"):
        build_llm_provider(settings, "local/qwen2.5:7b")


def test_custom_openai_model_joins_the_catalog():
    settings = _settings()
    settings.openai_model = "gpt-custom-text"
    ids = {row["id"] for row in openai_catalog_rows(settings)}
    assert "gpt-5.4-mini" in ids
    assert "gpt-custom-text" in ids
    assert is_openai_model("o3")
    assert not is_openai_model("openrouter/free")
    assert not is_openai_model("gemini-3.5-flash")
