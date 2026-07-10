"""Handle forwarded messages — buffer until user trigger or timeout."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from beachops.services.forward_context import get_forward_context_buffer
from beachops.services.telegram_feedback import mark_received

logger = logging.getLogger(__name__)


async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None or message.forward_origin is None:
        return

    buffer = get_forward_context_buffer(context)
    await buffer.add_forward(context, user_id=user.id, message=message)
    await mark_received(message)
    raise ApplicationHandlerStop
