"""Format forwarded Telegram messages for agent prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from telegram import (
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginHiddenUser,
    MessageOriginUser,
)


def message_is_forward(message: Message) -> bool:
    return message.forward_origin is not None


def _format_forward_date(message: Message) -> str:
    origin = message.forward_origin
    if origin is None:
        return ""
    dt = origin.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_forward_header(message: Message) -> str:
    origin = message.forward_origin
    if origin is None:
        return "[Message]"

    label = "Forwarded message"
    if isinstance(origin, MessageOriginUser):
        user = origin.sender_user
        name = user.username
        if name:
            label = f"Forwarded · @{name}"
        else:
            label = f"Forwarded · {user.full_name or user.first_name or 'user'}"
    elif isinstance(origin, MessageOriginHiddenUser):
        label = f"Forwarded · {origin.sender_user_name}"
    elif isinstance(origin, MessageOriginChat):
        chat = origin.sender_chat
        title = chat.title or chat.username or "chat"
        label = f"Forwarded · {title}"
        if origin.author_signature:
            label = f"{label} · {origin.author_signature}"
    elif isinstance(origin, MessageOriginChannel):
        chat = origin.chat
        title = chat.title or chat.username or "channel"
        label = f"Forwarded · {title}"
        if origin.author_signature:
            label = f"{label} · {origin.author_signature}"

    date_part = _format_forward_date(message)
    if date_part:
        return f"[{label} · {date_part}]"
    return f"[{label}]"


def format_forward_text_block(message: Message, body: str) -> str:
    text = body.strip()
    if not text:
        return format_forward_header(message)
    return f"{format_forward_header(message)}\n{text}"


def format_user_text_block(text: str) -> str:
    return f"[Your message]\n{text.strip()}"


def join_prompt_blocks(blocks: list[str]) -> str:
    cleaned = [b.strip() for b in blocks if b.strip()]
    return "\n\n---\n\n".join(cleaned)
