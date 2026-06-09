"""Cursor agent model presets exposed in the Telegram UI."""

from __future__ import annotations

from enum import Enum

from cursor_sdk import ModelParameterValue, ModelSelection


class CursorModelKey(str, Enum):
    COMPOSER_25 = "composer-2.5"
    OPUS_48 = "opus-4.8"
    GEMINI_35_FLASH = "gemini-3.5-flash"


_LEGACY_MODEL_KEYS: dict[str, str] = {
    "opus-4.6": CursorModelKey.OPUS_48.value,
}

CURSOR_MODEL_LABELS: dict[str, str] = {
    CursorModelKey.COMPOSER_25.value: "Composer 2.5",
    CursorModelKey.OPUS_48.value: "Opus 4.8",
    CursorModelKey.GEMINI_35_FLASH.value: "Gemini 3.5",
}

CURSOR_MODEL_ORDER: tuple[CursorModelKey, ...] = (
    CursorModelKey.COMPOSER_25,
    CursorModelKey.OPUS_48,
    CursorModelKey.GEMINI_35_FLASH,
)


def normalize_cursor_model_key(value: str | None, *, default: str) -> str:
    if value in _LEGACY_MODEL_KEYS:
        return _LEGACY_MODEL_KEYS[value]
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
    if key == CursorModelKey.OPUS_48.value:
        # API id: claude-opus-4-8. Context is 300k or 1m only (no 200k like 4.6).
        return ModelSelection(
            id="claude-opus-4-8",
            params=(
                ModelParameterValue(id="thinking", value="true"),
                ModelParameterValue(id="context", value="300k"),
                ModelParameterValue(id="effort", value="xhigh"),
                ModelParameterValue(id="fast", value="false"),
            ),
        )
    if key == CursorModelKey.GEMINI_35_FLASH.value:
        return "gemini-3.5-flash"
    return key
