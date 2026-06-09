"""Telegram application factory."""

from __future__ import annotations

import asyncio
import logging

from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.bot.handlers.agent import new_handler
from tg_cursor_bot.bot.handlers.agents import agents_handler
from tg_cursor_bot.bot.handlers.callbacks import callback_handler
from tg_cursor_bot.bot.handlers.cancel import cancel_handler
from tg_cursor_bot.bot.handlers.memory import memory_handler, remember_handler
from tg_cursor_bot.bot.handlers.mode import ask_handler, do_handler, mode_handler, plan_handler
from tg_cursor_bot.bot.handlers.repo import repo_handler
from tg_cursor_bot.bot.handlers.start import help_handler, start_handler
from tg_cursor_bot.bot.handlers.status import status_handler
from tg_cursor_bot.bot.handlers.text import text_handler
from tg_cursor_bot.bot.handlers.forward import forward_handler
from tg_cursor_bot.bot.handlers.document import document_handler
from tg_cursor_bot.bot.handlers.photo import photo_handler, register_media_group_collector
from tg_cursor_bot.services.forward_context import init_forward_context_buffer
from tg_cursor_bot.bot.handlers.voice import voice_handler
from tg_cursor_bot.config.settings import Settings
from tg_cursor_bot.services.bot_commands import register_bot_commands

_user_setup_locks: dict[int, asyncio.Lock] = {}


async def auth_gate(update: object, context) -> None:
    from telegram import Update

    if not isinstance(update, Update):
        return

    user = update.effective_user
    if user is None:
        return

    app: AppContext = context.application.bot_data["app"]
    if not app.settings.is_whitelisted(user.id):
        if update.message:
            await update.message.reply_text("Доступ запрещён.")
        elif update.callback_query:
            await update.callback_query.answer("Доступ запрещён.", show_alert=True)
        raise ApplicationHandlerStop

    is_new_user = False
    lock = _user_setup_locks.setdefault(user.id, asyncio.Lock())
    async with lock:
        is_new_user = await app.users.ensure_user(
            user.id, app.settings.is_admin(user.id)
        )
        if is_new_user and app.settings.has_default_repo():
            await app.repos.seed_default_repo_for_new_user(user.id, app.settings)
        else:
            await app.repos.resolve_active_repo(user.id, app.settings)


def register_handlers(application: Application) -> None:
    application.add_handler(TypeHandler(object, auth_gate), group=-1)

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("ask", ask_handler))
    application.add_handler(CommandHandler("plan", plan_handler))
    application.add_handler(CommandHandler("do", do_handler))
    application.add_handler(CommandHandler("mode", mode_handler))
    application.add_handler(CommandHandler("new", new_handler))
    application.add_handler(CommandHandler("agents", agents_handler))
    application.add_handler(CommandHandler("repo", repo_handler))
    application.add_handler(CommandHandler("remember", remember_handler))
    application.add_handler(CommandHandler("memory", memory_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("cancel", cancel_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.FORWARDED, forward_handler), group=0)
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.Document.IMAGE, photo_handler))
    document_filter = filters.Document.PDF | filters.Document.FileExtension("docx")
    application.add_handler(MessageHandler(document_filter, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))


def create_application(settings: Settings) -> Application:
    application = (
        Application.builder()
        .token(settings.tg_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    register_handlers(application)
    return application


async def _post_init(application: Application) -> None:
    from tg_cursor_bot.config.settings import get_settings

    settings = get_settings()
    application.bot_data["app"] = await AppContext.create(settings)
    register_media_group_collector(application)
    init_forward_context_buffer(application)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    await register_bot_commands(application)


async def _post_shutdown(application: Application) -> None:
    app: AppContext | None = application.bot_data.get("app")
    if app is not None:
        await app.close()
