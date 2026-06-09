"""Tests for Cursor model presets."""

from __future__ import annotations

from cursor_sdk import ModelSelection

from tg_cursor_bot.domain.cursor_models import (
    CursorModelKey,
    normalize_cursor_model_key,
    resolve_cursor_model,
)


def test_resolve_opus_48_uses_300k_xhigh() -> None:
    model = resolve_cursor_model(CursorModelKey.OPUS_48.value)
    assert isinstance(model, ModelSelection)
    assert model.id == "claude-opus-4-8"
    params = {p.id: p.value for p in model.params}
    assert params["context"] == "300k"
    assert params["effort"] == "xhigh"
    assert params["thinking"] == "true"


def test_normalize_legacy_opus_46() -> None:
    assert (
        normalize_cursor_model_key("opus-4.6", default="composer-2.5")
        == CursorModelKey.OPUS_48.value
    )


def test_normalize_unknown_falls_back_to_composer() -> None:
    assert normalize_cursor_model_key("unknown", default="composer-2.5") == "composer-2.5"
