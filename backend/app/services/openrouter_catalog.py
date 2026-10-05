"""Selectable OpenRouter models: free text output only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx

from app.config import Settings

SNAPSHOT_NAME = "openrouter_free_text_models.json"


class CatalogError(Exception):
    pass


def _price(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_free_text_model(model: dict[str, Any], *, today: date | None = None) -> bool:
    """True when the raw OpenRouter model record is a free text model."""

    today = today or date.today()
    pricing = model.get("pricing") or {}
    prompt = _price(pricing.get("prompt"))
    completion = _price(pricing.get("completion"))
    if prompt != 0 or completion != 0:
        return False
    modalities = (model.get("architecture") or {}).get("output_modalities") or []
    if set(modalities) != {"text"}:
        return False
    expiration = model.get("expiration_date")
    if expiration and str(expiration) < today.isoformat():
        return False
    return True


def normalize_model(model: dict[str, Any]) -> dict[str, Any]:
    params = set(model.get("supported_parameters") or [])
    architecture = model.get("architecture") or {}
    return {
        "id": model["id"],
        "name": model.get("name") or model["id"],
        "context_length": model.get("context_length"),
        "supports_json": "response_format" in params or "structured_outputs" in params,
        "expiration_date": model.get("expiration_date"),
        "modality": architecture.get("modality"),
    }


def snapshot_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / SNAPSHOT_NAME


def filter_free_text_models(
    raw_models: list[dict[str, Any]], *, today: date | None = None
) -> list[dict[str, Any]]:
    today = today or date.today()
    rows = [
        normalize_model(model)
        for model in raw_models
        if is_free_text_model(model, today=today)
    ]
    rows.sort(key=lambda row: str(row["name"]).casefold())
    return rows


def fetch_raw_models(base_url: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + "/models"
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        body = response.json()
    data = body.get("data")
    if not isinstance(data, list):
        raise CatalogError("OpenRouter /models response has no data list")
    return data


def load_snapshot(*, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    payload = json.loads(snapshot_path().read_text())
    rows = []
    for row in payload["models"]:
        expiration = row.get("expiration_date")
        if expiration and str(expiration) < today.isoformat():
            continue
        rows.append(row)
    rows.sort(key=lambda row: str(row["name"]).casefold())
    return rows


def write_snapshot(models: list[dict[str, Any]], *, source_url: str, fetched_on: date | None = None):
    fetched_on = fetched_on or date.today()
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source_url.rstrip("/") + "/models",
        "fetched_at": fetched_on.isoformat(),
        "models": models,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


@dataclass
class Catalog:
    source: str
    models: list[dict[str, Any]]
    default_model: str

    def ids(self) -> set[str]:
        return {str(model["id"]) for model in self.models}


def load_catalog(
    settings: Settings,
    *,
    today: date | None = None,
    fetcher: Callable[[], list[dict[str, Any]]] | None = None,
) -> Catalog:
    today = today or date.today()
    source = "snapshot"
    if settings.openrouter_catalog == "live":
        try:
            raw = fetcher() if fetcher else fetch_raw_models(settings.openrouter_base_url)
            models = filter_free_text_models(raw, today=today)
            if not models:
                models = load_snapshot(today=today)
            else:
                source = "live"
        except (httpx.HTTPError, OSError, CatalogError, json.JSONDecodeError, KeyError, ValueError):
            models = load_snapshot(today=today)
    else:
        models = load_snapshot(today=today)
    return Catalog(
        source=source,
        models=models,
        default_model=settings.openrouter_model,
    )
