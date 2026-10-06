"""Gemini generateContent for story JSON. OpenRouter stays the other text client."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable, _parse_json

_MODEL_ID = re.compile(r"^gemini-[A-Za-z0-9._-]+$")
_JSON_RETRY = "The previous reply was invalid: {error}. Reply with one JSON object only."

# Text models for story planning. Image, audio, and live models stay out of this list.
GEMINI_TEXT_MODELS: tuple[dict[str, Any], ...] = (
    {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash"},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite"},
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite"},
    {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash"},
    {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro"},
)


def is_gemini_model(model_id: str) -> bool:
    return bool(_MODEL_ID.fullmatch(model_id.strip()))


def gemini_catalog_rows(settings: Settings) -> list[dict[str, Any]]:
    rows = [
        {
            "id": model["id"],
            "name": model["name"],
            "provider": "gemini",
            "supports_json": True,
        }
        for model in GEMINI_TEXT_MODELS
    ]
    custom = settings.gemini_model.strip()
    if is_gemini_model(custom) and custom not in {row["id"] for row in rows}:
        rows.append({"id": custom, "name": custom, "provider": "gemini", "supports_json": True})
    return rows


class GeminiLLMProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        if not self.settings.gemini_api_key:
            raise ProviderUnavailable("Set GEMINI_API_KEY in .env before generating a story with Gemini.")
        if not is_gemini_model(self.settings.gemini_model):
            raise ProviderUnavailable(f"Unknown Gemini model: {self.settings.gemini_model}")
        prompt = user
        last_error = "empty response"
        for attempt in range(2):
            content = self._generate(system, prompt, schema, schema_name)
            try:
                return _parse_json(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                prompt = f"{user}\n\n{_JSON_RETRY.format(error=last_error)}"
                if attempt == 1:
                    raise ValueError(last_error) from exc
        raise ValueError(last_error)

    def _generate(self, system: str, user: str, schema: dict, schema_name: str) -> str:
        del schema_name
        response = self._post(self._body(system, user, schema, json_schema=True))
        if response.status_code == 400 and "schema" in response.text.lower():
            response = self._post(self._body(system, user, schema, json_schema=False))
        if response.status_code >= 400:
            raise ProviderUnavailable(f"Gemini returned {response.status_code}: {_error_text(response)}")
        return _candidate_text(response.json())

    def _body(self, system: str, user: str, schema: dict, *, json_schema: bool) -> dict:
        system_text = system
        generation: dict[str, Any] = {
            "temperature": 0.7,
            "maxOutputTokens": 32768,
            "responseMimeType": "application/json",
        }
        if json_schema:
            generation["responseJsonSchema"] = schema
        else:
            system_text = f"{system}\n\nJSON schema:\n{json.dumps(schema)}"
        return {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation,
        }

    def _post(self, body: dict) -> httpx.Response:
        model = quote(self.settings.gemini_model.strip(), safe="")
        url = self.settings.gemini_base_url.rstrip("/") + f"/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key,
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(url, headers=headers, json=body)
        with httpx.Client(timeout=180) as client:
            return client.post(url, headers=headers, json=body)


def _candidate_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        reason = feedback.get("blockReason") or "empty response"
        raise ValueError(f"Gemini returned no text ({reason})")
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict) and not part.get("thought")]
    text = "\n".join(piece for piece in texts if piece).strip()
    if not text:
        finish = candidates[0].get("finishReason") or "empty"
        raise ValueError(f"Gemini returned no JSON text ({finish})")
    return text


def _error_text(response: httpx.Response) -> str:
    try:
        message = (response.json().get("error") or {}).get("message")
        if message:
            return str(message)[:400]
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return response.text[:400]
