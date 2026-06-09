"""Tests for AnimatedStatus."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_cursor_bot.services.status_animation import AnimatedStatus


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    message = MagicMock()
    message.get_bot.return_value = AsyncMock()
    message.edit_text = AsyncMock()
    message.chat_id = 1

    anim = AnimatedStatus(message, preset="waiting")
    await anim.start()
    await anim.stop()
    await anim.stop()
    assert anim._stopped is True
