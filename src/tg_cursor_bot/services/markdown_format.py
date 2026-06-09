"""Convert agent Markdown to Telegram text + MessageEntity pairs."""

from __future__ import annotations

import logging

from telegram import MessageEntity as TgMessageEntity
from telegramify_markdown import convert, split_entities, utf16_len
from telegramify_markdown.entity import MessageEntity as TfyMessageEntity

from tg_cursor_bot.services.markdown_sanitize import (
    is_valid_telegram_link_url,
    make_telegram_safe_markdown,
    readable_plain,
    strip_poison_markdown,
)

logger = logging.getLogger(__name__)

_TELEGRAM_TEXT_LIMIT = 4096
_BODY_BUDGET_RESERVE = 80


class _ConversionFailed(Exception):
    """All convert() attempts failed."""


def _filter_invalid_link_entities(
    entities: list[TfyMessageEntity],
) -> list[TfyMessageEntity]:
    """Drop text_link entities Telegram rejects (non-http URLs)."""
    filtered: list[TfyMessageEntity] = []
    dropped = 0
    for entity in entities:
        if entity.type == "text_link" and not is_valid_telegram_link_url(entity.url):
            dropped += 1
            continue
        filtered.append(entity)
    if dropped:
        logger.info("markdown_gate=stripped_invalid_links count=%s", dropped)
    return filtered


def _to_telegram_entities(entities: list[TfyMessageEntity]) -> list[TgMessageEntity]:
    return [TgMessageEntity(**entity.to_dict()) for entity in entities]


def _shift_entities(
    entities: list[TfyMessageEntity],
    offset_utf16: int,
) -> list[TfyMessageEntity]:
    if offset_utf16 <= 0:
        return entities
    return [
        TfyMessageEntity(
            type=entity.type,
            offset=entity.offset + offset_utf16,
            length=entity.length,
            url=entity.url,
            language=entity.language,
            custom_emoji_id=entity.custom_emoji_id,
        )
        for entity in entities
    ]


def _prefix_suffix_blocks(prefix: str, suffix: str) -> tuple[str, str]:
    return prefix.rstrip(), suffix.strip()


def _join_message(prefix_block: str, body_text: str, suffix_block: str) -> str:
    segments: list[str] = []
    if prefix_block:
        segments.append(prefix_block)
    segments.append(body_text)
    if suffix_block:
        segments.append(suffix_block)
    return "\n\n".join(segments)


def _overhead_utf16(prefix_block: str, suffix_block: str) -> int:
    overhead = 0
    if prefix_block:
        overhead += utf16_len(prefix_block) + utf16_len("\n\n")
    if suffix_block:
        overhead += utf16_len("\n\n") + utf16_len(suffix_block)
    return overhead


def _convert_body(markdown: str) -> tuple[str, list[TfyMessageEntity], str]:
    """Return (body_text, entities, gate_status)."""
    safe = make_telegram_safe_markdown(markdown)
    try:
        body_text, body_entities = convert(safe)
        return body_text, body_entities, "ok"
    except Exception:
        logger.warning("markdown convert failed (safe pass)", exc_info=True)

    poison = strip_poison_markdown(markdown)
    try:
        body_text, body_entities = convert(poison)
        return body_text, body_entities, "retry"
    except Exception:
        logger.warning("markdown convert failed (poison pass)", exc_info=True)

    raise _ConversionFailed


def _truncate_body(
    body_text: str,
    body_entities: list[TfyMessageEntity],
    body_budget: int,
) -> tuple[str, list[TfyMessageEntity], bool]:
    if body_budget <= 0 or utf16_len(body_text) <= body_budget:
        return body_text, body_entities, False
    chunks = split_entities(body_text, body_entities, body_budget)
    truncated = len(chunks) > 1
    text, entities = chunks[0]
    if truncated:
        text = text.rstrip() + "\n\n…"
    return text, entities, truncated


def format_readable_message(
    prefix: str,
    markdown_body: str,
    suffix: str = "",
) -> str:
    """Plain Telegram text without entities; markdown syntax stripped."""
    body = markdown_body.strip()
    if not body:
        return ""
    prefix_block, suffix_block = _prefix_suffix_blocks(prefix, suffix)
    plain_body = readable_plain(body)
    text = _join_message(prefix_block, plain_body, suffix_block)
    if utf16_len(text) > _TELEGRAM_TEXT_LIMIT:
        text = text[:4090] + "…"
    return text


def format_markdown_message(
    prefix: str,
    markdown_body: str,
    suffix: str = "",
) -> tuple[str, list[TgMessageEntity] | None] | None:
    """Return Telegram-ready text and optional entities.

    - Success: (text, entities)
    - convert() failed: (text, None) with readable_plain body
    - Empty body: None
    """
    body = markdown_body.strip()
    if not body:
        return None

    prefix_block, suffix_block = _prefix_suffix_blocks(prefix, suffix)
    prefix_sep = f"{prefix_block}\n\n" if prefix_block else ""
    overhead = _overhead_utf16(prefix_block, suffix_block)
    body_budget = max(256, _TELEGRAM_TEXT_LIMIT - overhead - _BODY_BUDGET_RESERVE)

    gate_status = "readable_plain"
    try:
        body_text, body_entities, gate_status = _convert_body(body)
        body_entities = _filter_invalid_link_entities(body_entities)
        body_text, body_entities, _ = _truncate_body(body_text, body_entities, body_budget)
        full_text = _join_message(prefix_block, body_text, suffix_block)
        body_offset = utf16_len(prefix_sep)
        entities = _shift_entities(body_entities, body_offset)

        if utf16_len(full_text) > _TELEGRAM_TEXT_LIMIT:
            chunks = split_entities(full_text, entities, _TELEGRAM_TEXT_LIMIT)
            full_text, entities = chunks[0]
            if len(chunks) > 1:
                full_text = full_text.rstrip() + "\n\n…"
                gate_status = f"{gate_status}+truncated"

        logger.info("markdown_gate=%s body_len=%s", gate_status, len(body))
        return full_text, _to_telegram_entities(entities)
    except _ConversionFailed:
        logger.info("markdown_gate=readable_plain body_len=%s", len(body))
        return format_readable_message(prefix, body, suffix), None
