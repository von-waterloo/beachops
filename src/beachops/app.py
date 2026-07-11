"""Telegram application factory."""

from __future__ import annotations

import asyncio

from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.constants import ChatType

from beachops.app_context import AppContext
from beachops.bot.handlers.agent import new_handler
from beachops.bot.handlers.agents import agents_handler
from beachops.bot.handlers.callbacks import callback_handler
from beachops.bot.handlers.cancel import cancel_handler
from beachops.bot.handlers.control_plane import approvals_handler, jobs_handler
from beachops.bot.handlers.dashboard import dashboard_handler
from beachops.bot.handlers.rollback import rollback_handler
from beachops.bot.handlers.memory import memory_handler, remember_handler
from beachops.bot.handlers.mode import ask_handler, do_handler, mode_handler, plan_handler
from beachops.bot.handlers.repo import repo_handler
from beachops.bot.handlers.start import help_handler, start_handler
from beachops.bot.handlers.status import status_handler
from beachops.bot.handlers.text import text_handler
from beachops.bot.handlers.forward import forward_handler
from beachops.bot.handlers.document import document_handler
from beachops.bot.handlers.photo import photo_handler
from beachops.services.forward_context import init_forward_context_buffer
from beachops.bot.handlers.unsupported import unsupported_media_handler
from beachops.services.cursor_model_catalog import validate_ui_models
from beachops.services.prompt_coalesce import init_prompt_coalesce
from beachops.services.telegram_images import init_media_group_collector
from beachops.bot.handlers.voice import voice_handler
from beachops.config.settings import Settings
from beachops.services.bot_commands import register_bot_commands

_user_setup_locks: dict[int, asyncio.Lock] = {}


async def auth_gate(update: object, context) -> None:
    from telegram import Update

    if not isinstance(update, Update):
        return

    user = update.effective_user
    if user is None:
        return

    app: AppContext = context.application.bot_data["app"]
    chat = update.effective_chat
    if chat is not None and chat.type != ChatType.PRIVATE:
        if update.message:
            await update.message.reply_text("BeachOps работает только в личном чате.")
        elif update.callback_query:
            await update.callback_query.answer(
                "Откройте BeachOps в личном чате.",
                show_alert=True,
            )
        raise ApplicationHandlerStop

    if not app.settings.is_whitelisted(user.id):
        if update.message:
            await update.message.reply_text(
                "Доступ запрещён. Обратитесь к администратору бота."
            )
        elif update.callback_query:
            await update.callback_query.answer("Доступ запрещён.", show_alert=True)
        raise ApplicationHandlerStop

    is_new_user = False
    role = app.settings.role_for(user.id)
    role_value = role.value if role is not None else "none"
    cached_role = await app.hot_cache.get_user_ready_role(user.id)
    if cached_role == role_value:
        return

    lock = _user_setup_locks.setdefault(user.id, asyncio.Lock())
    async with lock:
        cached_role = await app.hot_cache.get_user_ready_role(user.id)
        if cached_role == role_value:
            return
        is_new_user = await app.users.ensure_user(
            user.id,
            app.settings.is_admin(user.id),
            role=role,
        )
        if (
            is_new_user
            and app.settings.has_default_repo()
            and app.repository_policy.is_allowed(
                app.settings.default_repo_url,
                app.settings.default_branch,
            )
        ):
            await app.repos.seed_default_repo_for_new_user(user.id, app.settings)
        else:
            await app.repos.resolve_active_repo(user.id, app.settings)
        await app.hot_cache.set_user_ready(user.id, role_value)


def register_handlers(application: Application) -> None:
    application.add_handler(TypeHandler(object, auth_gate), group=-1)

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("ask", ask_handler))
    application.add_handler(CommandHandler("plan", plan_handler))
    application.add_handler(CommandHandler("do", do_handler))
    application.add_handler(CommandHandler("task", plan_handler))
    application.add_handler(CommandHandler("mode", mode_handler))
    application.add_handler(CommandHandler("new", new_handler))
    application.add_handler(CommandHandler("agents", agents_handler))
    application.add_handler(CommandHandler("repo", repo_handler))
    application.add_handler(CommandHandler("remember", remember_handler))
    application.add_handler(CommandHandler("memory", memory_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("cancel", cancel_handler))
    application.add_handler(CommandHandler("jobs", jobs_handler))
    application.add_handler(CommandHandler("approvals", approvals_handler))
    application.add_handler(CommandHandler("rollback", rollback_handler))
    application.add_handler(CommandHandler("dashboard", dashboard_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.FORWARDED, forward_handler), group=0)
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.Document.IMAGE, photo_handler))
    document_filter = filters.Document.PDF | filters.Document.FileExtension("docx")
    application.add_handler(MessageHandler(document_filter, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, unsupported_media_handler),
        group=99,
    )


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
    from telegram import Message

    from beachops.config.settings import get_settings
    from beachops.services.prompt_coalesce import get_prompt_coalesce
    from beachops.services.run_executor import validate_prompt_request
    from beachops.services.telegram_feedback import mark_received
    from types import SimpleNamespace

    settings = get_settings()
    application.bot_data["app"] = await AppContext.create(settings)
    init_prompt_coalesce(application)

    async def on_media_group_flush(user_id: int, messages: list[Message]) -> None:
        app: AppContext = application.bot_data["app"]
        error = await validate_prompt_request(app, user_id)
        if error:
            anchor = messages[0] if messages else None
            if anchor is not None:
                await anchor.reply_text(error)
            return
        ctx = SimpleNamespace(application=application, bot=application.bot)
        coalesce = get_prompt_coalesce(ctx)
        if messages:
            app.remember_user_message(user_id, messages[0].message_id or 0)
        for msg in messages:
            await mark_received(msg)
            await coalesce.add_photo(ctx, user_id=user_id, message=msg)

    init_media_group_collector(application, on_flush=on_media_group_flush)
    init_forward_context_buffer(application)
    validate_ui_models(settings.cursor_api_key)
    await register_bot_commands(application)


async def _post_shutdown(application: Application) -> None:
    app: AppContext | None = application.bot_data.get("app")
    if app is not None:
        await app.close()
