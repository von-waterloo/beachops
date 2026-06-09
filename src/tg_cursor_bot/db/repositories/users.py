"""User repository."""

from __future__ import annotations

import asyncpg

from tg_cursor_bot.domain.cursor_models import CursorModelKey, normalize_cursor_model_key
from tg_cursor_bot.domain.models import UserMode


class UserRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_user(self, tg_user_id: int, is_admin: bool) -> bool:
        """Ensure user row exists. Returns True only on first insert (new user)."""
        async with self._pool.acquire() as conn:
            existed = await conn.fetchval(
                "SELECT 1 FROM users WHERE tg_user_id = $1",
                tg_user_id,
            )
            await conn.execute(
                """
                INSERT INTO users (tg_user_id, is_admin, current_mode, cursor_model_key)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tg_user_id) DO UPDATE SET
                    is_admin = EXCLUDED.is_admin,
                    current_mode = CASE
                        WHEN EXCLUDED.is_admin THEN users.current_mode
                        ELSE 'ask'
                    END
                """,
                tg_user_id,
                is_admin,
                UserMode.ASK.value,
                CursorModelKey.COMPOSER_25.value,
            )
        return existed is None

    async def get_mode(self, tg_user_id: int) -> UserMode:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_mode FROM users WHERE tg_user_id = $1",
                tg_user_id,
            )
        if row is None:
            return UserMode.ASK
        return UserMode(row["current_mode"])

    async def set_mode(self, tg_user_id: int, mode: UserMode) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET current_mode = $1 WHERE tg_user_id = $2",
                mode.value,
                tg_user_id,
            )

    async def get_cursor_model_key(self, tg_user_id: int, *, default: str) -> str:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT cursor_model_key FROM users WHERE tg_user_id = $1",
                tg_user_id,
            )
        if row is None:
            return normalize_cursor_model_key(None, default=default)
        return normalize_cursor_model_key(row["cursor_model_key"], default=default)

    async def set_cursor_model_key(self, tg_user_id: int, model_key: str) -> None:
        normalized = normalize_cursor_model_key(model_key, default=model_key)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET cursor_model_key = $1 WHERE tg_user_id = $2",
                normalized,
                tg_user_id,
            )
