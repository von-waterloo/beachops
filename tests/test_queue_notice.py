"""Tests for queue notice visibility and dismissal."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from beachops.services.queue_notice import (
    dismiss_queue_notice,
    pop_queue_notice,
    remember_queue_notice,
    should_show_queue_notice,
)


@pytest.mark.asyncio
async def test_should_show_when_waiting_behind_active_run() -> None:
    job_id = uuid4()
    app = SimpleNamespace(
        jobs=SimpleNamespace(
            queue_position=AsyncMock(return_value=1),
            latest_active_for_actor=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        ),
    )
    show, position = await should_show_queue_notice(app, 42, job_id)  # type: ignore[arg-type]
    assert show is True
    assert position == 1


@pytest.mark.asyncio
async def test_should_hide_when_first_and_no_active_run() -> None:
    job_id = uuid4()
    app = SimpleNamespace(
        jobs=SimpleNamespace(
            queue_position=AsyncMock(return_value=1),
            latest_active_for_actor=AsyncMock(return_value=None),
        ),
    )
    show, position = await should_show_queue_notice(app, 42, job_id)  # type: ignore[arg-type]
    assert show is False
    assert position == 0


@pytest.mark.asyncio
async def test_remember_and_pop_queue_notice() -> None:
    job_id = uuid4()
    redis = SimpleNamespace(
        set=AsyncMock(),
        getdel=AsyncMock(
            return_value=b'{"chat_id": 42, "message_id": 99}',
        ),
    )
    app = SimpleNamespace(redis=redis)
    await remember_queue_notice(app, job_id=job_id, chat_id=42, message_id=99)  # type: ignore[arg-type]
    ref = await pop_queue_notice(app, job_id=job_id)  # type: ignore[arg-type]
    assert ref is not None
    assert ref.chat_id == 42
    assert ref.message_id == 99


@pytest.mark.asyncio
async def test_dismiss_queue_notice_deletes_telegram_message() -> None:
    job_id = uuid4()
    app = SimpleNamespace(
        redis=SimpleNamespace(
            getdel=AsyncMock(
                return_value=b'{"chat_id": 42, "message_id": 99}',
            ),
        ),
    )
    bot = SimpleNamespace(delete_message=AsyncMock())
    await dismiss_queue_notice(bot, app, job_id=job_id)  # type: ignore[arg-type]
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=99)
