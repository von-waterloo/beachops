"""Ephemeral Telegram «Запрос в очереди» cards — show while waiting, delete on start."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from beachops.app_context import AppContext

logger = logging.getLogger(__name__)

_PREFIX = "beachops:queue-notice:"
_LEGACY_PREFIX = "beachops:queue-notice:legacy:"
_TTL_SEC = 86_400


@dataclass(frozen=True, slots=True)
class QueueNoticeRef:
    chat_id: int
    message_id: int


async def should_show_queue_notice(
    app: AppContext,
    actor_id: int,
    job_id: UUID,
) -> tuple[bool, int]:
    """Return (show_notice, display_position) for a durable queued job."""
    position = await app.jobs.queue_position(actor_id, job_id)
    if position <= 0:
        return False, 0
    active = await app.jobs.latest_active_for_actor(actor_id)
    if position > 1 or active is not None:
        return True, position
    return False, 0


async def remember_queue_notice(
    app: AppContext,
    *,
    chat_id: int,
    message_id: int,
    job_id: UUID | None = None,
    user_id: int | None = None,
) -> None:
    key = _key(job_id=job_id, user_id=user_id)
    payload = json.dumps({"chat_id": chat_id, "message_id": message_id}, separators=(",", ":"))
    await app.redis.set(key, payload.encode("utf-8"), ex=_TTL_SEC)


async def pop_queue_notice(
    app: AppContext,
    *,
    job_id: UUID | None = None,
    user_id: int | None = None,
) -> QueueNoticeRef | None:
    key = _key(job_id=job_id, user_id=user_id)
    raw = await app.redis.getdel(key)
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
        return QueueNoticeRef(
            chat_id=int(data["chat_id"]),
            message_id=int(data["message_id"]),
        )
    except (KeyError, TypeError, ValueError):
        logger.debug("Invalid queue notice payload for %s", key)
        return None


async def dismiss_queue_notice(
    bot,
    app: AppContext,
    *,
    job_id: UUID | None = None,
    user_id: int | None = None,
) -> None:
    ref = await pop_queue_notice(app, job_id=job_id, user_id=user_id)
    if ref is None:
        return
    try:
        await bot.delete_message(chat_id=ref.chat_id, message_id=ref.message_id)
    except Exception:
        logger.debug(
            "Could not delete queue notice chat=%s msg=%s",
            ref.chat_id,
            ref.message_id,
            exc_info=True,
        )


def _key(*, job_id: UUID | None, user_id: int | None) -> str:
    if job_id is not None:
        return f"{_PREFIX}{job_id}"
    if user_id is not None:
        return f"{_LEGACY_PREFIX}{user_id}"
    raise ValueError("job_id or user_id required")
