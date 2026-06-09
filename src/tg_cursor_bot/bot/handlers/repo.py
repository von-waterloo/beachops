"""Repository management."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.services.inline_keyboards import repo_list_keyboard
from tg_cursor_bot.services.repo_parse import parse_repo_add_args, repo_add_usage
from tg_cursor_bot.services.ui_copy import (
    repo_empty,
    repo_list_header,
    repo_list_line,
    repo_not_found,
    repo_saved,
    repo_switched,
)


async def repo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    assert user is not None and update.message

    args = context.args or []

    if len(args) >= 1 and args[0] == "add":
        parsed = parse_repo_add_args(
            args,
            default_branch=app.settings.default_branch,
        )
        if parsed is None:
            await update.message.reply_text(repo_add_usage())
            return
        make_active = len(await app.repos.list_repos(user.id)) == 0
        repo = await app.repos.add_repo(
            user.id,
            alias=parsed.alias,
            github_url=parsed.github_url,
            default_branch=parsed.default_branch,
            make_active=make_active,
        )
        await update.message.reply_text(repo_saved(repo.alias, is_active=repo.is_active))
        return

    if len(args) == 1:
        alias = args[0]
        repo = await app.repos.set_active(user.id, alias)
        if repo is None:
            await update.message.reply_text(repo_not_found(alias))
            return
        await app.agent_slots.sync_active_slot_repo(user.id, repo)
        await update.message.reply_text(repo_switched(repo.alias))
        return

    repos = await app.repos.list_repos(user.id)
    if not repos:
        await update.message.reply_text(repo_empty(app.settings.default_branch))
        return

    lines = [repo_list_header(), ""]
    lines.extend(repo_list_line(r) for r in repos)
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=repo_list_keyboard(repos),
    )
