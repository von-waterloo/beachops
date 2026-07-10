"""Shared /agents list rendering."""

from __future__ import annotations

from telegram import Bot, InlineKeyboardMarkup

from beachops.app_context import AppContext
from beachops.services.inline_keyboards import (
    agent_slots_keyboard,
    paginate_agent_slots,
)
from beachops.services.ui_copy import agent_list_header, agent_list_line


def build_agent_list_text(slots, *, page: int = 0) -> str:
    page_slots, page, total_pages = paginate_agent_slots(slots, page)
    lines = [agent_list_header(page=page, total_pages=total_pages), ""]
    lines.extend(agent_list_line(s) for s in page_slots)
    return "\n".join(lines)


def build_agent_list_markup(
    app: AppContext, slots, *, page: int = 0
) -> InlineKeyboardMarkup:
    _, page, _ = paginate_agent_slots(slots, page)
    can_create = len(slots) < app.agent_slots.max_slots
    can_delete = len(slots) > 1
    return agent_slots_keyboard(
        slots,
        page=page,
        can_create=can_create,
        can_delete=can_delete,
    )


async def send_agent_list(
    *,
    bot: Bot,
    chat_id: int,
    app: AppContext,
    user_id: int,
    page: int = 0,
) -> None:
    await app.agent_slots.ensure_default_slot(user_id)
    slots = await app.agent_slots.list_slots(user_id)
    await bot.send_message(
        chat_id=chat_id,
        text=build_agent_list_text(slots, page=page),
        reply_markup=build_agent_list_markup(app, slots, page=page),
    )


async def edit_agent_list_page(
    *,
    message,
    app: AppContext,
    user_id: int,
    page: int,
) -> None:
    slots = await app.agent_slots.list_slots(user_id)
    await message.edit_text(
        build_agent_list_text(slots, page=page),
        reply_markup=build_agent_list_markup(app, slots, page=page),
    )
