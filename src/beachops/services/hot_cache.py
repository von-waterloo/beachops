"""Short-lived Redis read caches for hot paths.

Not a general KV layer — only the spots where repeated Postgres/OpenAI
round-trips dominate latency and brief staleness is acceptable.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

_USER_READY_PREFIX = "beachops:cache:user_ready:"
_DASHBOARD_PREFIX = "beachops:cache:dashboard:"
_DASHBOARD_GEN_KEY = "beachops:cache:dash_gen"
_PANIC_KEY = "beachops:cache:panic"

USER_READY_TTL_SEC = 900
DASHBOARD_TTL_SEC = 3
PANIC_TTL_SEC = 3600


class HotCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_user_ready_role(self, user_id: int) -> str | None:
        raw = await self._redis.get(f"{_USER_READY_PREFIX}{user_id}")
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    async def set_user_ready(self, user_id: int, role: str) -> None:
        await self._redis.set(
            f"{_USER_READY_PREFIX}{user_id}",
            role.encode("utf-8"),
            ex=USER_READY_TTL_SEC,
        )

    async def dashboard_generation(self) -> int:
        raw = await self._redis.get(_DASHBOARD_GEN_KEY)
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    async def bump_dashboard_generation(self) -> None:
        await self._redis.incr(_DASHBOARD_GEN_KEY)

    def _dashboard_key(self, scope: str, generation: int) -> str:
        return f"{_DASHBOARD_PREFIX}{generation}:{scope}"

    async def get_dashboard(self, scope: str) -> dict[str, Any] | None:
        generation = await self.dashboard_generation()
        raw = await self._redis.get(self._dashboard_key(scope, generation))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    async def set_dashboard(self, scope: str, payload: dict[str, Any]) -> None:
        generation = await self.dashboard_generation()
        await self._redis.set(
            self._dashboard_key(scope, generation),
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            ),
            ex=DASHBOARD_TTL_SEC,
        )

    async def get_panic(self) -> bool | None:
        """Return cached panic flag, or None on miss."""
        raw = await self._redis.get(_PANIC_KEY)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw == b"1"
        return str(raw) == "1"

    async def warm_panic(self, enabled: bool) -> None:
        """Fill panic cache without invalidating dashboard snapshots."""
        await self._redis.set(
            _PANIC_KEY,
            b"1" if enabled else b"0",
            ex=PANIC_TTL_SEC,
        )

    async def set_panic(self, enabled: bool) -> None:
        await self.warm_panic(enabled)
        await self.bump_dashboard_generation()
