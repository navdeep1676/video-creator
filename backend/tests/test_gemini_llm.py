import json

import httpx
import pytest

from app.config import Settings
from app.services.gemini_llm import GeminiLLMProvider, gemini_catalog_rows, is_gemini_model
from app.services.openrouter_llm import ProviderUnavailable
from app.services.story_job import build_llm_provider


def _settings() -> Settings:
    return Settings(
        gemini_api_key="gem-key",
        gemini_model="gemini-3.5-flash",
        openrouter_api_key="or-key",
        openrouter_model="openrouter/free",
    )


def test_gemini_parses_json_and_skips_thoughts():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "gem-key"
        assert request.url.path.endswith("/models/gemini-3.5-flash:generateContent")
        body = json.loads(request.content.decode())
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["type"] == "object"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "planning"},
                                {"text": '{"title": "ok"}'},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    provider = GeminiLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    parsed = provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan")
    assert parsed == {"title": "ok"}


def test_schema_rejection_retries_without_response_schema():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        if "responseJsonSchema" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "responseJsonSchema is not supported"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"title": "ok"}'}]}}]})

    provider = GeminiLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan") == {
        "title": "ok"
    }
    assert "responseJsonSchema" not in calls[1]["generationConfig"]
    assert "JSON schema" in calls[1]["systemInstruction"]["parts"][0]["text"]


def test_invalid_json_retries_once():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "nope" if calls["n"] == 1 else '{"title": "ok"}'
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": content}]}}]})

    provider = GeminiLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan")[
        "title"
    ] == "ok"
    assert calls["n"] == 2


def test_missing_gemini_key_does_not_call_the_api():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("generateContent should not be called without a key")

    settings = _settings()
    settings.gemini_api_key = ""
    provider = GeminiLLMProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderUnavailable, match="GEMINI_API_KEY"):
        provider.complete_json(system="sys", user="write", schema={}, schema_name="story_plan")


def test_http_error_is_provider_unavailable():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota exceeded"}})

    provider = GeminiLLMProvider(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderUnavailable, match="429"):
        provider.complete_json(system="sys", user="write", schema={"type": "object"}, schema_name="story_plan")


def test_build_llm_provider_routes_by_model_id():
    settings = _settings()
    assert isinstance(build_llm_provider(settings, "gemini-3.8-flash"), GeminiLLMProvider)
    assert build_llm_provider(settings, "gemini-3.8-flash").settings.gemini_model == "gemini-3.8-flash"
    assert not isinstance(build_llm_provider(settings, "openrouter/free"), GeminiLLMProvider)


def test_custom_gemini_model_joins_the_catalog():
    settings = _settings()
    settings.gemini_model = "gemini-custom-text"
    ids = {row["id"] for row in gemini_catalog_rows(settings)}
    assert "gemini-3.5-flash" in ids
    assert "gemini-custom-text" in ids
    assert is_gemini_model("gemini-3.5-flash")
    assert not is_gemini_model("openrouter/free")
    assert not is_gemini_model("gemini-../etc")
