"""Tests for Cursor model presets and dynamic keys."""

from __future__ import annotations

from beachops.domain.cursor_models import (
    CursorModelKey,
    normalize_cursor_model_key,
    resolve_cursor_model,
)
from beachops.services.cursor_cloud_client import ModelParam, ModelSelection
from beachops.services.cursor_model_catalog import (
    apply_catalog_variant,
    parse_catalog_item,
    selection_fingerprint,
    selection_to_ui_key,
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


def test_resolve_opus_5_uses_complete_catalog_variant() -> None:
    model = resolve_cursor_model(CursorModelKey.OPUS_5.value)
    assert isinstance(model, ModelSelection)
    assert model.id == "claude-opus-5"
    params = {p.id: p.value for p in model.params}
    assert params == {
        "cyber": "false",
        "thinking": "true",
        "context": "300k",
        "effort": "high",
        "fast": "false",
    }


def test_normalize_legacy_sonnet_5_maps_to_opus_5() -> None:
    assert (
        normalize_cursor_model_key("sonnet-5", default="composer-2.5")
        == CursorModelKey.OPUS_5.value
    )


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


def test_resolve_dyn_key_with_params() -> None:
    model = resolve_cursor_model("dyn:custom-model|thinking=true,effort=low")
    assert isinstance(model, ModelSelection)
    assert model.id == "custom-model"
    assert {p.id: p.value for p in model.params} == {
        "thinking": "true",
        "effort": "low",
    }


def test_selection_fingerprint_is_stable_and_short() -> None:
    a = ModelSelection(id="x", params=())
    b = ModelSelection(id="x", params=())
    assert selection_fingerprint(a) == selection_fingerprint(b)
    assert len(selection_fingerprint(a)) == 10
    assert selection_to_ui_key(a).startswith("dyn:x")


def _grok_catalog_item() -> dict:
    return {
        "id": "grok-4.6",
        "displayName": "Cursor Grok 4.6",
        "parameters": [
            {
                "id": "effort",
                "values": [{"value": "low"}, {"value": "medium"}, {"value": "high"}],
            },
            {"id": "fast", "values": [{"value": "false"}, {"value": "true"}]},
        ],
        "variants": [
            {
                "params": [
                    {"id": "effort", "value": "low"},
                    {"id": "fast", "value": "false"},
                ]
            },
            {
                "params": [
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "true"},
                ],
                "isDefault": True,
            },
        ],
    }


def _opus_catalog_item() -> dict:
    return {
        "id": "claude-opus-5",
        "displayName": "Claude Opus 5",
        "aliases": ["opus-5", "opus"],
        "parameters": [
            {"id": "thinking", "values": [{"value": "false"}, {"value": "true"}]},
            {"id": "context", "values": [{"value": "300k"}, {"value": "1m"}]},
            {"id": "effort", "values": [{"value": "low"}, {"value": "high"}]},
            {"id": "fast", "values": [{"value": "false"}, {"value": "true"}]},
        ],
        "variants": [
            {
                "params": [
                    {"id": "cyber", "value": "false"},
                    {"id": "thinking", "value": "true"},
                    {"id": "context", "value": "300k"},
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "false"},
                ]
            },
            {
                "params": [
                    {"id": "cyber", "value": "false"},
                    {"id": "thinking", "value": "true"},
                    {"id": "context", "value": "1m"},
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "false"},
                ],
                "isDefault": True,
            },
        ],
    }


def test_parse_catalog_uses_default_variant_not_first_enum() -> None:
    parsed = parse_catalog_item(_grok_catalog_item())
    assert parsed is not None
    assert parsed.id == "grok-4.6"
    assert {p.id: p.value for p in parsed.params} == {
        "effort": "high",
        "fast": "true",
    }


def test_parse_catalog_includes_variant_params_missing_from_parameter_defs() -> None:
    parsed = parse_catalog_item(_opus_catalog_item())
    assert parsed is not None
    assert {p.id: p.value for p in parsed.params}["cyber"] == "false"
    assert parsed.aliases == ("opus-5", "opus")


def test_apply_catalog_completes_incomplete_opus_params() -> None:
    catalog = parse_catalog_item(_opus_catalog_item())
    assert catalog is not None
    incomplete = ModelSelection(
        id="claude-opus-5",
        params=(
            ModelParam(id="thinking", value="true"),
            ModelParam(id="context", value="300k"),
            ModelParam(id="effort", value="high"),
        ),
    )
    coerced = apply_catalog_variant(incomplete, [catalog])
    assert isinstance(coerced, ModelSelection)
    assert {p.id: p.value for p in coerced.params} == {
        "cyber": "false",
        "thinking": "true",
        "context": "300k",
        "effort": "high",
        "fast": "false",
    }


def test_apply_catalog_snaps_bare_grok_id_to_default_variant() -> None:
    catalog = parse_catalog_item(_grok_catalog_item())
    assert catalog is not None
    coerced = apply_catalog_variant("grok-4.6", [catalog])
    assert isinstance(coerced, ModelSelection)
    assert {p.id: p.value for p in coerced.params} == {
        "effort": "high",
        "fast": "true",
    }


def test_apply_catalog_replaces_garbage_params_with_default_variant() -> None:
    catalog = parse_catalog_item(_grok_catalog_item())
    assert catalog is not None
    broken = ModelSelection(
        id="grok-4.6",
        params=(ModelParam(id="effort", value="{'value': 'low'}"),),
    )
    coerced = apply_catalog_variant(broken, [catalog])
    assert isinstance(coerced, ModelSelection)
    assert {p.id: p.value for p in coerced.params} == {
        "effort": "high",
        "fast": "true",
    }
