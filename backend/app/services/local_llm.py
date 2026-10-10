"""OpenAI-compatible local story models (Ollama or LM Studio)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable, _parse_json

_JSON_RETRY = "The previous reply was invalid: {error}. Reply with one JSON object only."
_PREFIX = "local/"


def is_local_model(model_id: str) -> bool:
    text = (model_id or "").strip()
    if not text.startswith(_PREFIX):
        return False
    name = text[len(_PREFIX) :]
    return bool(name) and ".." not in name and not any(char.isspace() for char in name)


def local_model_name(model_id: str) -> str:
    text = model_id.strip()
    if text.startswith(_PREFIX):
        return text[len(_PREFIX) :]
    return text


def configured_local_model(settings: Settings) -> str:
    """Story-model id from LOCAL_LLM_MODEL, or empty when it is unset."""
    stored = _stored_id(settings.local_llm_model) if settings.local_llm_model.strip() else ""
    if stored and is_local_model(stored):
        return stored
    return ""


def _stored_id(model_id: str) -> str:
    text = model_id.strip()
    if text.startswith(_PREFIX):
        return text
    return f"{_PREFIX}{text}"


def local_catalog_rows(settings: Settings, client: httpx.Client | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Return catalog rows and whether the local server answered."""
    found, available = _fetch_ids(settings, client)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    custom = settings.local_llm_model.strip()
    if custom and is_local_model(_stored_id(custom)):
        stored = _stored_id(custom)
        seen.add(stored)
        rows.append(
            {
                "id": stored,
                "name": local_model_name(stored),
                "provider": "local",
                "supports_json": True,
            }
        )
    for model_id in found:
        stored = _stored_id(model_id)
        if not is_local_model(stored) or stored in seen:
            continue
        seen.add(stored)
        rows.append(
            {
                "id": stored,
                "name": local_model_name(stored),
                "provider": "local",
                "supports_json": True,
            }
        )
    return rows, available


def _fetch_ids(settings: Settings, client: httpx.Client | None) -> tuple[list[str], bool]:
    url = settings.local_llm_base_url.rstrip("/") + "/models"
    try:
        if client is not None:
            response = client.get(url)
        else:
            with httpx.Client(timeout=3) as http:
                response = http.get(url)
        response.raise_for_status()
        data = response.json().get("data") or []
    except (httpx.HTTPError, OSError, ValueError, AttributeError):
        return [], False
    ids: list[str] = []
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("id"):
                ids.append(str(row["id"]))
    return ids, True


class LocalLLMProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        if not is_local_model(self.settings.local_llm_model):
            raise ProviderUnavailable(f"Unknown local model: {self.settings.local_llm_model}")
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
            raise ProviderUnavailable(f"Local model returned {response.status_code}: {_error_text(response)}")
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
            "model": local_model_name(self.settings.local_llm_model),
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user},
            ],
            "response_format": response_format,
        }
        if temperature:
            body["temperature"] = 0.7
        if "11434" in self.settings.local_llm_base_url:
            body["keep_alive"] = 0
        return body

    def _post(self, body: dict) -> httpx.Response:
        url = self.settings.local_llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.local_llm_api_key.strip():
            headers["Authorization"] = f"Bearer {self.settings.local_llm_api_key.strip()}"
        try:
            if self._client is not None:
                return self._client.post(url, headers=headers, json=body)
            with httpx.Client(timeout=300) as client:
                return client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "Local model server is not reachable at "
                f"{self.settings.local_llm_base_url}. Start Ollama or LM Studio, then load a text model."
            ) from exc


def _message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("Local model returned no choices")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        finish = choices[0].get("finish_reason") or "empty"
        raise ValueError(f"Local model returned no JSON text ({finish})")
    return text


def _error_text(response: httpx.Response) -> str:
    try:
        message = (response.json().get("error") or {}).get("message")
        if message:
            return str(message)[:400]
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return response.text[:400]
