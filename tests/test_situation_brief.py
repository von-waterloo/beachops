"""Tests for control-room situation brief injection."""

from __future__ import annotations

from beachops.services.situation_brief import with_situation


def test_with_situation_prepends_brief() -> None:
    result = with_situation("Сделай фикс", "Ситуация:\n- Очередь: активно 0")
    assert result.startswith("Ситуация:")
    assert "Запрос пользователя:\nСделай фикс" in result


def test_with_situation_empty_brief_returns_prompt() -> None:
    assert with_situation("hello", None) == "hello"
    assert with_situation("hello", "  ") == "hello"


def test_with_situation_empty_prompt_returns_brief() -> None:
    assert with_situation("", "brief only") == "brief only"
