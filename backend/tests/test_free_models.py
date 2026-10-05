from datetime import date

from app.services.openrouter_catalog import is_free_text_model, load_catalog, load_snapshot


TODAY = date(2026, 10, 5)


def _model(model_id, prompt, completion, outputs, expiration=None):
    record = {
        "id": model_id,
        "name": model_id,
        "pricing": {"prompt": prompt, "completion": completion},
        "architecture": {"modality": "text->text", "output_modalities": outputs},
        "supported_parameters": ["response_format"],
        "context_length": 8192,
    }
    if expiration:
        record["expiration_date"] = expiration
    return record


def test_free_text_filter_keeps_only_zero_price_text_models():
    free = _model("google/gemma-4-31b-it:free", "0", "0", ["text"])
    paid = _model("qwen/qwen3-14b", "0.00000012", "0.00000024", ["text"])
    variable = _model("typesafe/jev-router", "-1", "-1", ["text"])
    audio = _model("google/lyria-3-pro-preview", "0", "0", ["text", "audio"])
    expired = _model("old/free", "0", "0", ["text"], expiration="2026-10-04")
    through_today = _model("stealth/space-bunny-alpha", "0", "0", ["text"], expiration="2026-10-05")

    assert is_free_text_model(free, today=TODAY)
    assert is_free_text_model(through_today, today=TODAY)
    assert not is_free_text_model(paid, today=TODAY)
    assert not is_free_text_model(variable, today=TODAY)
    assert not is_free_text_model(audio, today=TODAY)
    assert not is_free_text_model(expired, today=TODAY)


def test_snapshot_is_the_filtered_catalog():
    rows = load_snapshot(today=TODAY)
    ids = {row["id"] for row in rows}
    assert "openrouter/free" in ids
    assert "qwen/qwen3.8-27b:free" in ids
    assert "google/gemma-4-31b-it:free" in ids
    assert "nvidia/nemotron-3.5-content-safety:free" in ids
    assert "qwen/qwen3-14b" not in ids
    assert len(rows) == 20
    assert len(ids) == len(rows)


def test_live_catalog_filters_and_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_CATALOG", "live")
    from app.config import Settings

    settings = Settings()
    raw = [
        _model("qwen/qwen3-14b", "0.00000012", "0.00000024", ["text"]),
        _model("google/gemma-4-31b-it:free", "0", "0", ["text"]),
    ]
    live = load_catalog(settings, today=TODAY, fetcher=lambda: raw)
    assert live.source == "live"
    assert [row["id"] for row in live.models] == ["google/gemma-4-31b-it:free"]

    def down():
        raise OSError("catalog down")

    fallback = load_catalog(settings, today=TODAY, fetcher=down)
    assert fallback.source == "snapshot"
    assert "openrouter/free" in fallback.ids()
