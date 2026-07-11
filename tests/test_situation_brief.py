"""Tests for situation brief injection."""

from __future__ import annotations

from beachops.services.situation_brief import (
    ControlRoomCounts,
    format_spoken_room,
    with_situation,
)


def test_with_situation_prepends_brief() -> None:
    result = with_situation("Сделай фикс", "Ситуация:\n- Очередь: активно 0")
    assert result.startswith("Ситуация:")
    assert "Запрос пользователя:\nСделай фикс" in result


def test_with_situation_empty_brief_returns_prompt() -> None:
    assert with_situation("hello", None) == "hello"
    assert with_situation("hello", "  ") == "hello"


def test_with_situation_empty_prompt_returns_brief() -> None:
    assert with_situation("", "brief only") == "brief only"


def test_format_spoken_room_always_silent() -> None:
    assert (
        format_spoken_room(
            ControlRoomCounts(
                running=3,
                queued=2,
                blocked=2,
                pending_approvals=1,
                workers_online=1,
            )
        )
        == ""
    )
