"""Open the authenticated BeachOps Telegram Mini App."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.services.inline_keyboards import dashboard_keyboard
from beachops.services.ui_copy import dashboard_message, dashboard_unavailable
from beachops.services.webapp_url import webapp_open_url


async def dashboard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.message
    if message is None:
        return
    app: AppContext = context.application.bot_data["app"]
    url = webapp_open_url(
        str(getattr(app.settings, "webapp_base_url", "")),
        version=str(getattr(app.settings, "webapp_build_id", "")),
    )
    if not url or not url.lower().startswith("https://"):
        await message.reply_text(dashboard_unavailable())
        return
    await message.reply_text(
        dashboard_message(),
        reply_markup=dashboard_keyboard(url),
    )
