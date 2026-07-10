"""Tests for run result delivery helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from beachops.domain.models import UserMode
from beachops.services.run_executor import _maybe_send_result_document


async def test_long_answer_is_preserved_as_markdown_document() -> None:
    bot = SimpleNamespace(send_document=AsyncMock())
    context = SimpleNamespace(bot=bot)
    state = SimpleNamespace(
        plan_text=None,
        plan_name=None,
        final_text="x" * 3001,
        assistant_text="",
    )

    await _maybe_send_result_document(context, 42, UserMode.ASK, state)

    bot.send_document.assert_awaited_once()
    kwargs = bot.send_document.await_args.kwargs
    assert kwargs["chat_id"] == 42
    assert kwargs["filename"] == "cursor_answer.md"
    assert kwargs["document"] == ("x" * 3001).encode()


async def test_short_answer_does_not_send_document() -> None:
    bot = SimpleNamespace(send_document=AsyncMock())
    context = SimpleNamespace(bot=bot)
    state = SimpleNamespace(
        plan_text=None,
        plan_name=None,
        final_text="коротко",
        assistant_text="",
    )

    await _maybe_send_result_document(context, 42, UserMode.DO, state)

    bot.send_document.assert_not_awaited()


async def test_long_plan_keeps_plan_filename() -> None:
    bot = SimpleNamespace(send_document=AsyncMock())
    context = SimpleNamespace(bot=bot)
    state = SimpleNamespace(
        plan_text="п" * 3001,
        plan_name="Новый API",
        final_text="intro",
        assistant_text="",
    )

    await _maybe_send_result_document(context, 42, UserMode.PLAN, state)

    assert bot.send_document.await_args.kwargs["filename"] == "Новый_API.md"
