"""Pending inline rename state in Telegram user_data."""

from __future__ import annotations

from telegram.ext import ContextTypes

_USER_DATA_KEY = "agent_rename_slot_id"


def set_pending(context: ContextTypes.DEFAULT_TYPE, slot_id: int) -> None:
    context.user_data[_USER_DATA_KEY] = slot_id


def peek_pending(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    value = context.user_data.get(_USER_DATA_KEY)
    return int(value) if isinstance(value, int) else None


def clear_pending(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    value = context.user_data.pop(_USER_DATA_KEY, None)
    return int(value) if isinstance(value, int) else None
