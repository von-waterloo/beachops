"""Cursor agent model presets exposed in the Telegram UI."""

from __future__ import annotations

from enum import Enum

from cursor_sdk import ModelParameterValue, ModelSelection


class CursorModelKey(str, Enum):
    COMPOSER_25 = "composer-2.5"
    FABLE_5 = "fable-5"
    SONNET_5 = "sonnet-5"
    GPT_56_TERRA = "gpt-5.6-terra"


CURSOR_MODEL_LABELS: dict[str, str] = {
    CursorModelKey.COMPOSER_25.value: "Composer 2.5",
    CursorModelKey.FABLE_5.value: "Fable 5",
    CursorModelKey.SONNET_5.value: "Sonnet 5",
    CursorModelKey.GPT_56_TERRA.value: "GPT-5.6 Terra",
}

CURSOR_MODEL_ORDER: tuple[CursorModelKey, ...] = (
    CursorModelKey.COMPOSER_25,
    CursorModelKey.FABLE_5,
    CursorModelKey.SONNET_5,
    CursorModelKey.GPT_56_TERRA,
)


def normalize_cursor_model_key(value: str | None, *, default: str) -> str:
    if value in {item.value for item in CursorModelKey}:
        return value  # type: ignore[return-value]
    if default in {item.value for item in CursorModelKey}:
        return default
    return CursorModelKey.COMPOSER_25.value


def cursor_model_label(key: str) -> str:
    return CURSOR_MODEL_LABELS.get(key, key)


def resolve_cursor_model(key: str) -> str | ModelSelection:
    """Map UI key to cursor-sdk model id or ModelSelection with variants."""
    if key == CursorModelKey.COMPOSER_25.value:
        return ModelSelection(
            id="composer-2.5",
            params=(ModelParameterValue(id="fast", value="true"),),
        )
    if key == CursorModelKey.FABLE_5.value:
        return ModelSelection(
            id="claude-fable-5",
            params=(
                ModelParameterValue(id="thinking", value="true"),
                ModelParameterValue(id="context", value="300k"),
                ModelParameterValue(id="effort", value="high"),
            ),
        )
    if key == CursorModelKey.SONNET_5.value:
        return ModelSelection(
            id="claude-sonnet-5",
            params=(
                ModelParameterValue(id="thinking", value="true"),
                ModelParameterValue(id="context", value="300k"),
                ModelParameterValue(id="effort", value="medium"),
            ),
        )
    if key == CursorModelKey.GPT_56_TERRA.value:
        return ModelSelection(
            id="gpt-5.6-terra",
            params=(
                ModelParameterValue(id="context", value="272k"),
                ModelParameterValue(id="reasoning", value="medium"),
                ModelParameterValue(id="fast", value="false"),
            ),
        )
    return key
