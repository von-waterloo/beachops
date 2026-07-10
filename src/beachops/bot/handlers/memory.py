"""Memory commands: /remember and /memory."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.memory_present import build_memory_list
from beachops.services.ui_copy import (
    memory_empty,
    memory_item_line,
    memory_note_saved,
    memory_search_header,
    no_repo_selected,
)


async def remember_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message is not None

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "Использование: /remember текст заметки\n"
            "Пример: /remember dev — основная ветка"
        )
        return

    repo = await app.repos.get_active_repo(user.id)
    if repo is None:
        await update.message.reply_text(no_repo_selected())
        return

    entry_id = await app.memory.add_note(
        tg_user_id=user.id,
        repo_id=repo.id,
        text=parts[1].strip(),
    )
    await update.message.reply_text(memory_note_saved(entry_id))


async def memory_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message is not None

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    repo = await app.repos.get_active_repo(user.id)

    if len(parts) > 1 and parts[1].strip():
        query = parts[1].strip()
        items = await app.memory.search(
            user.id,
            query,
            repo_id=repo.id if repo else None,
        )
        if not items:
            await update.message.reply_text(memory_empty())
            return
        lines = [memory_search_header(query)]
        lines.extend(memory_item_line(item) for item in items)
        await update.message.reply_text("\n".join(lines))
        return

    body, markup = await build_memory_list(app, user.id)
    if body is None:
        await update.message.reply_text(memory_empty())
        return
    await update.message.reply_text(body, reply_markup=markup)
