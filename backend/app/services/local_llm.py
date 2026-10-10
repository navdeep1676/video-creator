"""OpenAI-compatible local story models (Ollama or LM Studio)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.services.openrouter_llm import ProviderUnavailable, _parse_json

logger = logging.getLogger(__name__)

_JSON_RETRY = "The previous reply was invalid: {error}. Reply with one JSON object only."
_PREFIX = "local/"
# qwen2.5:7b is the story default. On this GPU a local 7B/8B story is about 24 tokens per second.
# A 5 minute read timeout killed a 7,000 token reply and the UI called the server down.
_CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=900.0, write=60.0, pool=10.0)
_MAX_TOKENS = 12288


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


def ollama_root(settings: Settings) -> str:
    root = settings.local_llm_base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root


def ollama_is_local(settings: Settings) -> bool:
    host = (urlparse(settings.local_llm_base_url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"} and "11434" in settings.local_llm_base_url


def should_manage_ollama(settings: Settings, model: str, *, injected_provider: bool) -> bool:
    """True when a story should start Ollama and unload Qwen when the story ends."""
    if injected_provider or not settings.ollama_manage_process:
        return False
    if not is_local_model(model) or not ollama_is_local(settings):
        return False
    return True


def _ollama_exe() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "Programs" / "Ollama" / "ollama.exe"


def ollama_is_up(settings: Settings) -> bool:
    try:
        response = httpx.get(ollama_root(settings) + "/api/version", timeout=2)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def ensure_ollama_server(settings: Settings) -> None:
    """Start `ollama serve` when a local story needs Qwen and nothing is listening."""
    if ollama_is_up(settings):
        return
    exe = _ollama_exe()
    if not exe.is_file():
        raise ProviderUnavailable(
            f"Ollama was not found at {exe}. Local stories need Ollama on port 11434."
        )
    logger.info("Starting Ollama at %s", ollama_root(settings))
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [str(exe), "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if ollama_is_up(settings):
            return
        time.sleep(1)
    raise ProviderUnavailable("Ollama did not answer /api/version within 60 seconds.")


def release_ollama_model(settings: Settings, model: str) -> None:
    """Unload Qwen and stop its runner so the GPU is free after the story."""
    if not is_local_model(model):
        return
    name = local_model_name(model)
    try:
        httpx.post(
            ollama_root(settings) + "/api/generate",
            json={"model": name, "keep_alive": 0},
            timeout=30,
        )
    except httpx.HTTPError:
        logger.info("Ollama unload request failed for %s", name)
    _stop_llama_server()


def _stop_llama_server() -> None:
    if os.name != "nt":
        return
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'llama-server.exe' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    listed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    pids = [line.strip() for line in listed.stdout.splitlines() if line.strip().isdigit()]
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, check=False)
    if pids:
        logger.info("Stopped the Qwen runner so the GPU is free")


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
        use_think = True
        use_limit = True
        response = self._post(
            self._body(
                system,
                user,
                schema,
                schema_name,
                json_schema=use_schema,
                temperature=use_temperature,
                think=use_think,
                limit=use_limit,
            )
        )
        if response.status_code == 400:
            text = response.text.lower()
            if any(phrase in text for phrase in ("response_format", "json_schema", "schema")):
                use_schema = False
            if "temperature" in text:
                use_temperature = False
            if "think" in text:
                use_think = False
            if "max_tokens" in text or "max tokens" in text:
                use_limit = False
            if not use_schema or not use_temperature or not use_think or not use_limit:
                response = self._post(
                    self._body(
                        system,
                        user,
                        schema,
                        schema_name,
                        json_schema=use_schema,
                        temperature=use_temperature,
                        think=use_think,
                        limit=use_limit,
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
        think: bool,
        limit: bool,
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
        if limit:
            body["max_tokens"] = _MAX_TOKENS
        if "11434" in self.settings.local_llm_base_url:
            body["keep_alive"] = 0
            # qwen3 spends the whole reply on reasoning unless this is off.
            if think:
                body["think"] = False
        return body

    def _post(self, body: dict) -> httpx.Response:
        url = self.settings.local_llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.local_llm_api_key.strip():
            headers["Authorization"] = f"Bearer {self.settings.local_llm_api_key.strip()}"
        try:
            if self._client is not None:
                return self._client.post(url, headers=headers, json=body)
            with httpx.Client(timeout=_CHAT_TIMEOUT) as client:
                return client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc

    def _transport_error(self, exc: httpx.HTTPError) -> ProviderUnavailable:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return ProviderUnavailable(
                "Local model server is not reachable at "
                f"{self.settings.local_llm_base_url}. Start Ollama or LM Studio, then load a text model."
            )
        if isinstance(exc, httpx.TimeoutException):
            return ProviderUnavailable(
                "The local model is running, but the story was still being written after 15 minutes. "
                "Generate again. A shorter length finishes sooner."
            )
        return ProviderUnavailable(
            f"The local model request failed: {exc}. Check the server at {self.settings.local_llm_base_url}."
        )


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
