"""OpenRouter chat completions."""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.services.openrouter_catalog import filter_free_text_models


class ProviderUnavailable(RuntimeError):
    pass


class LLMProvider(Protocol):
    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        """Return one JSON object. Raise ProviderUnavailable when the service cannot be called."""

_JSON_RETRY = "The previous reply was invalid: {error}. Reply with one JSON object only."


class OpenRouterLLMProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        if not self.settings.openrouter_api_key:
            raise ProviderUnavailable("Set OPENROUTER_API_KEY in .env before generating a story.")
        prompt = user
        last_error = "empty response"
        for attempt in range(2):
            content = self._chat(system, prompt, schema, schema_name)
            try:
                return _parse_json(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                prompt = f"{user}\n\n{_JSON_RETRY.format(error=last_error)}"
                if attempt == 1:
                    raise ValueError(last_error) from exc
        raise ValueError(last_error)

    def _chat(self, system: str, user: str, schema: dict, schema_name: str) -> str:
        body = self._body(system, user, schema, schema_name, json_schema=True)
        response = self._post("/chat/completions", body)
        if response.status_code == 400 and "response_format" in response.text.lower():
            body = self._body(system, user, schema, schema_name, json_schema=False)
            response = self._post("/chat/completions", body)
        if _unknown_model(response):
            ids = self._free_ids()
            raise ProviderUnavailable("Unknown OpenRouter model. Free text models: " + ", ".join(ids))
        if response.status_code >= 400:
            raise ProviderUnavailable(f"OpenRouter returned {response.status_code}: {response.text[:400]}")
        payload = response.json()
        return str(payload["choices"][0]["message"].get("content") or "")

    def _body(self, system: str, user: str, schema: dict, schema_name: str, *, json_schema: bool) -> dict:
        system_text = system
        response_format: dict[str, Any]
        if json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}
            system_text = f"{system}\n\nJSON schema:\n{json.dumps(schema)}"
        return {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "response_format": response_format,
        }

    def _post(self, path: str, body: dict | None = None) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        url = self.settings.openrouter_base_url.rstrip("/") + path
        if self._client is not None:
            if body is None:
                return self._client.get(url, headers=headers)
            return self._client.post(url, headers=headers, json=body)
        with httpx.Client(timeout=120) as client:
            if body is None:
                return client.get(url, headers=headers)
            return client.post(url, headers=headers, json=body)

    def _free_ids(self) -> list[str]:
        try:
            response = self._post("/models")
            response.raise_for_status()
            return [row["id"] for row in filter_free_text_models(response.json().get("data") or [])]
        except (httpx.HTTPError, OSError, ValueError, KeyError):
            return []


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text[: text.rfind("```")]
        text = text.strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON root must be an object")
    return parsed


def _unknown_model(response: httpx.Response) -> bool:
    if response.status_code == 404:
        return True
    text = response.text.lower()
    return response.status_code == 400 and "model" in text and any(
        phrase in text for phrase in ("not found", "unknown", "no endpoints", "invalid model")
    )
