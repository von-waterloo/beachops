"""Shared memory list rendering for /memory and nav button."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup

from beachops.app_context import AppContext
from beachops.services.inline_keyboards import memory_keyboard
from beachops.services.ui_copy import memory_empty, memory_header, memory_item_line


async def build_memory_list(
    app: AppContext,
    user_id: int,
) -> tuple[str | None, InlineKeyboardMarkup | None]:
    """Return (text, keyboard) or (None, None) when memory is empty."""
    repo = await app.repos.get_active_repo(user_id)
    repo_id = repo.id if repo else None
    items = await app.memory.list_recent(user_id, repo_id=repo_id)
    if not items:
        return None, None

    runs = await app.memory.list_runs_for_retry(
        user_id,
        repo_id=repo_id,
        limit=app.settings.memory_list_limit,
    )
    lines = [memory_header()]
    lines.extend(memory_item_line(item) for item in items)
    return "\n".join(lines), memory_keyboard(runs)
