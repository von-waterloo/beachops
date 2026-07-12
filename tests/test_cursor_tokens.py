"""Tests for mt/mt2/mt3 token keys."""

from __future__ import annotations

from beachops.domain.cursor_tokens import (
    DEFAULT_CURSOR_TOKEN_KEY,
    CursorTokenKey,
    cursor_token_label,
    normalize_cursor_token_key,
)


def test_normalize_valid_keys() -> None:
    assert normalize_cursor_token_key("mt") == "mt"
    assert normalize_cursor_token_key("mt2") == "mt2"
    assert normalize_cursor_token_key("mt3") == "mt3"


def test_normalize_invalid_falls_back_to_default() -> None:
    assert normalize_cursor_token_key(None) == DEFAULT_CURSOR_TOKEN_KEY
    assert normalize_cursor_token_key("unknown") == DEFAULT_CURSOR_TOKEN_KEY
    assert DEFAULT_CURSOR_TOKEN_KEY == CursorTokenKey.MT.value


def test_labels() -> None:
    assert cursor_token_label("mt") == "mt"
    assert cursor_token_label("mt2") == "mt2"
    assert cursor_token_label("mt3") == "mt3"
