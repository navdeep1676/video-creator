"""OpenAI chat completions for story JSON."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable, _parse_json

_MODEL_ID = re.compile(r"^(gpt-[A-Za-z0-9._-]+|o[0-9][A-Za-z0-9._-]*|chatgpt-[A-Za-z0-9._-]+)$")
_JSON_RETRY = "The previous reply was invalid: {error}. Reply with one JSON object only."

# Text models for story planning. Image, audio, realtime, and Codex models stay out.
OPENAI_TEXT_MODELS: tuple[dict[str, Any], ...] = (
    {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini"},
    {"id": "gpt-5.4-nano", "name": "GPT-5.4 Nano"},
    {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna"},
    {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra"},
    {"id": "gpt-5.4", "name": "GPT-5.4"},
    {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini"},
    {"id": "gpt-4.1", "name": "GPT-4.1"},
)


def is_openai_model(model_id: str) -> bool:
    return bool(_MODEL_ID.fullmatch(model_id.strip()))


def openai_catalog_rows(settings: Settings) -> list[dict[str, Any]]:
    rows = [
        {
            "id": model["id"],
            "name": model["name"],
            "provider": "openai",
            "supports_json": True,
        }
        for model in OPENAI_TEXT_MODELS
    ]
    custom = settings.openai_model.strip()
    if is_openai_model(custom) and custom not in {row["id"] for row in rows}:
        rows.append({"id": custom, "name": custom, "provider": "openai", "supports_json": True})
    return rows


class OpenAILLMProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        if not self.settings.openai_api_key:
            raise ProviderUnavailable("Set OPENAI_API_KEY in .env before generating a story with OpenAI.")
        if not is_openai_model(self.settings.openai_model):
            raise ProviderUnavailable(f"Unknown OpenAI model: {self.settings.openai_model}")
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
        use_schema = True
        use_temperature = True
        response = self._post(self._body(system, user, schema, schema_name, json_schema=True, temperature=True))
        if response.status_code == 400:
            text = response.text.lower()
            if any(phrase in text for phrase in ("response_format", "json_schema", "schema")):
                use_schema = False
            if "temperature" in text:
                use_temperature = False
            if not use_schema or not use_temperature:
                response = self._post(
                    self._body(
                        system,
                        user,
                        schema,
                        schema_name,
                        json_schema=use_schema,
                        temperature=use_temperature,
                    )
                )
        if response.status_code >= 400:
            raise ProviderUnavailable(f"OpenAI returned {response.status_code}: {_error_text(response)}")
        return _message_text(response.json())

    def _body(
        self,
        system: str,
        user: str,
        schema: dict,
        schema_name: str,
        *,
        json_schema: bool,
        temperature: bool,
    ) -> dict:
        system_text = system
        if json_schema:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}
            system_text = f"{system}\n\nJSON schema:\n{json.dumps(schema)}"
        body: dict[str, Any] = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user},
            ],
            "response_format": response_format,
        }
        if temperature:
            body["temperature"] = 0.7
        return body

    def _post(self, body: dict) -> httpx.Response:
        url = self.settings.openai_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(url, headers=headers, json=body)
        with httpx.Client(timeout=180) as client:
            return client.post(url, headers=headers, json=body)


def _message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("OpenAI returned no choices")
    message = choices[0].get("message") or {}
    refusal = message.get("refusal")
    if refusal:
        raise ValueError(f"OpenAI refused the story request: {refusal}")
    text = str(message.get("content") or "").strip()
    if not text:
        finish = choices[0].get("finish_reason") or "empty"
        raise ValueError(f"OpenAI returned no JSON text ({finish})")
    return text


def _error_text(response: httpx.Response) -> str:
    try:
        message = (response.json().get("error") or {}).get("message")
        if message:
            return str(message)[:400]
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return response.text[:400]
