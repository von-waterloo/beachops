"""Lightweight Telegram UX feedback helpers."""

from __future__ import annotations

import logging

from telegram import Message, ReactionTypeEmoji
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

_RECEIVED = ReactionTypeEmoji("👀")


async def mark_received(message: Message) -> None:
    try:
        await message.set_reaction([_RECEIVED])
    except BadRequest:
        logger.debug("set_reaction unsupported or failed", exc_info=True)
    except Exception:
        logger.debug("set_reaction failed", exc_info=True)


async def clear_reaction(message: Message) -> None:
    try:
        await message.set_reaction([])
    except BadRequest:
        pass
    except Exception:
        logger.debug("clear reaction failed", exc_info=True)
