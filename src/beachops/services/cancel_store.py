"""Cross-process cancel flags via Redis (bot ↔ worker)."""

from __future__ import annotations

from redis.asyncio import Redis

_CANCEL_KEY = "beachops:cancel:{actor_id}"
_CANCEL_TTL_SEC = 7200


class CancelStore:
    """Durable cancel signal shared by bot and ARQ worker processes."""

    def __init__(self, redis: Redis, *, ttl_sec: int = _CANCEL_TTL_SEC) -> None:
        self._redis = redis
        self._ttl_sec = max(60, ttl_sec)

    def _key(self, actor_id: int) -> str:
        return _CANCEL_KEY.format(actor_id=actor_id)

    async def request_cancel(self, actor_id: int) -> None:
        await self._redis.set(self._key(actor_id), b"1", ex=self._ttl_sec)

    async def clear_cancel(self, actor_id: int) -> None:
        await self._redis.delete(self._key(actor_id))

    async def is_cancelled(self, actor_id: int) -> bool:
        return bool(await self._redis.exists(self._key(actor_id)))
