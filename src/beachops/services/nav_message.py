"""Edit-in-place helpers for inline navigation screens."""

from __future__ import annotations

from telegram.error import BadRequest


async def edit_or_reply(message, *, text: str, reply_markup=None) -> None:
    """Prefer editing the source message; fall back to a new reply on failure."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        lowered = str(exc).lower()
        if "message is not modified" in lowered:
            return
        await message.reply_text(text, reply_markup=reply_markup)
