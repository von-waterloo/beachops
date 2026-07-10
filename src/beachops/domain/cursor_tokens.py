"""Cursor API token presets exposed in the Telegram UI."""

from __future__ import annotations

from enum import Enum


class CursorTokenKey(str, Enum):
    MT = "mt"
    MT2 = "mt2"


DEFAULT_CURSOR_TOKEN_KEY = CursorTokenKey.MT.value

CURSOR_TOKEN_LABELS: dict[str, str] = {
    CursorTokenKey.MT.value: "mt",
    CursorTokenKey.MT2.value: "mt2",
}

CURSOR_TOKEN_ORDER: tuple[CursorTokenKey, ...] = (
    CursorTokenKey.MT,
    CursorTokenKey.MT2,
)


def normalize_cursor_token_key(value: str | None) -> str:
    if value in {item.value for item in CursorTokenKey}:
        return value  # type: ignore[return-value]
    return DEFAULT_CURSOR_TOKEN_KEY


def cursor_token_label(key: str) -> str:
    return CURSOR_TOKEN_LABELS.get(key, key)
