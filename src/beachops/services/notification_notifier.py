"""Idempotent Telegram notifier driven by notification outbox."""

from __future__ import annotations

import json
import logging
from typing import Any

from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from beachops.app_context import AppContext

logger = logging.getLogger(__name__)


class NotificationNotifier:
    def __init__(self, app: AppContext, bot: Bot) -> None:
        self._app = app
        self._bot = bot

    async def drain(self, *, limit: int = 20) -> int:
        items = await self._app.notification_outbox.claim_pending(limit=limit)
        sent = 0
        for item in items:
            try:
                await self._deliver(item)
                await self._app.notification_outbox.mark_sent(int(item["id"]))
                sent += 1
            except RetryAfter as exc:
                await self._app.notification_outbox.mark_failed(
                    int(item["id"]),
                    error=f"retry_after:{exc.retry_after}",
                    retry_in_sec=int(exc.retry_after) + 1,
                )
            except (TimedOut, NetworkError) as exc:
                await self._app.notification_outbox.mark_failed(
                    int(item["id"]),
                    error=str(exc),
                    retry_in_sec=20,
                )
            except Exception as exc:
                logger.exception("Notifier failed for outbox %s", item.get("id"))
                await self._app.notification_outbox.mark_failed(
                    int(item["id"]),
                    error=str(exc),
                    retry_in_sec=30,
                )
        return sent

    async def _deliver(self, item: dict[str, Any]) -> None:
        payload = item.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        chat_id = item.get("telegram_chat_id") or item.get("actor_id")
        message_id = item.get("telegram_message_id") or payload.get("telegram_message_id")
        kind = str(item.get("kind") or "update")

        if kind == "edit" and message_id:
            try:
                await self._bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    text=text[:4096],
                )
                return
            except BadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
                # Never duplicate a finished run message with a fallback send.
                logger.warning(
                    "edit failed; skipping send fallback to avoid duplicate: %s",
                    exc,
                )
                return

        await self._bot.send_message(chat_id=int(chat_id), text=text[:4096])
