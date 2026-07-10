"""Tests for Cursor model presets."""

from __future__ import annotations

from cursor_sdk import ModelSelection

from beachops.domain.cursor_models import (
    CursorModelKey,
    normalize_cursor_model_key,
    resolve_cursor_model,
)


def test_resolve_fable_5_matches_catalog_variant() -> None:
    model = resolve_cursor_model(CursorModelKey.FABLE_5.value)
    assert isinstance(model, ModelSelection)
    assert model.id == "claude-fable-5"
    params = {p.id: p.value for p in model.params}
    assert params == {
        "thinking": "true",
        "context": "300k",
        "effort": "high",
    }


def test_resolve_sonnet_5_uses_moderate_preset() -> None:
    model = resolve_cursor_model(CursorModelKey.SONNET_5.value)
    assert isinstance(model, ModelSelection)
    assert model.id == "claude-sonnet-5"
    params = {p.id: p.value for p in model.params}
    assert params == {
        "thinking": "true",
        "context": "300k",
        "effort": "medium",
    }


def test_resolve_gpt_56_terra_uses_standard_context_and_medium_reasoning() -> None:
    model = resolve_cursor_model(CursorModelKey.GPT_56_TERRA.value)
    assert isinstance(model, ModelSelection)
    assert model.id == "gpt-5.6-terra"
    params = {p.id: p.value for p in model.params}
    assert params == {
        "context": "272k",
        "reasoning": "medium",
        "fast": "false",
    }


def test_normalize_unknown_falls_back_to_composer() -> None:
    assert normalize_cursor_model_key("unknown", default="composer-2.5") == "composer-2.5"


def test_normalize_unknown_falls_back_to_default_when_valid() -> None:
    assert (
        normalize_cursor_model_key("unknown", default=CursorModelKey.FABLE_5.value)
        == CursorModelKey.FABLE_5.value
    )
