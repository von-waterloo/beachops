"""Replay-safe idempotency claims backed by Redis."""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis


class IdempotencyStore:
    def __init__(self, redis: Redis, *, prefix: str = "beachops:idem") -> None:
        self._redis = redis
        self._prefix = prefix

    async def claim(self, namespace: str, key: str, *, ttl_sec: int = 3600) -> bool:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = f"{self._prefix}:{namespace}:{digest}"
        return bool(
            await self._redis.set(
                redis_key,
                "1",
                ex=max(1, ttl_sec),
                nx=True,
            )
        )
