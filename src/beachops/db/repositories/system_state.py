"""Durable global control-plane state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import asyncpg

from beachops.domain.security import Role
from beachops.services.authz import require_owner
from beachops.services.hot_cache import HotCache


class SystemStateRepository:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        cache: HotCache | None = None,
    ) -> None:
        self._pool = pool
        self._cache = cache

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT value FROM system_state WHERE key = $1",
                key,
            )
        return _json_object(value) if value is not None else None

    async def set(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        actor_id: int,
        actor_role: Role,
    ) -> None:
        require_owner(actor_role)
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO system_state (key, value, updated_by, updated_at)
                SELECT $1, $2::jsonb, tg_user_id, now()
                FROM users
                WHERE tg_user_id = $3 AND role = 'owner'
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING key
                """,
                key,
                encoded,
                actor_id,
            )
        if row is None:
            raise PermissionError("owner role required")

    async def is_panic_enabled(self) -> bool:
        if self._cache is not None:
            cached = await self._cache.get_panic()
            if cached is not None:
                return cached
        enabled = bool((await self.get("panic") or {}).get("enabled") is True)
        if self._cache is not None:
            await self._cache.warm_panic(enabled)
        return enabled

    async def set_panic(
        self,
        enabled: bool,
        *,
        actor_id: int,
        actor_role: Role,
    ) -> None:
        await self.set(
            "panic",
            {"enabled": enabled},
            actor_id=actor_id,
            actor_role=actor_role,
        )
        if self._cache is not None:
            await self._cache.set_panic(enabled)


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}
