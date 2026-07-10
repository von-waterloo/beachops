"""Redis-backed rate and concurrency controls."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis


_INCREMENT_SCRIPT = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return value
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_sec: int


class RedisRateLimiter:
    def __init__(self, redis: Redis, *, prefix: str = "beachops:rate") -> None:
        self._redis = redis
        self._prefix = prefix

    async def check(
        self,
        *,
        subject: str,
        action: str,
        limit: int,
        window_sec: int,
    ) -> RateLimitResult:
        key = f"{self._prefix}:{action}:{subject}"
        count = int(
            await self._redis.eval(
                _INCREMENT_SCRIPT,
                1,
                key,
                max(1, window_sec),
            )
        )
        ttl = int(await self._redis.ttl(key))
        return RateLimitResult(
            allowed=count <= limit,
            remaining=max(0, limit - count),
            retry_after_sec=max(1, ttl),
        )
