"""WebAuthn credential persistence."""

from __future__ import annotations

import asyncpg


class PasskeyRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def has_any(self, user_id: int) -> bool:
        async with self._pool.acquire() as conn:
            return bool(
                await conn.fetchval(
                    "SELECT EXISTS("
                    "SELECT 1 FROM webauthn_credentials WHERE user_id = $1"
                    ")",
                    user_id,
                )
            )

    async def list_for_user(self, user_id: int) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT credential_id, transports, label, created_at, last_used_at
                FROM webauthn_credentials
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [dict(row) for row in rows]

    async def get(self, credential_id: bytes) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT credential_id, user_id, public_key, sign_count,
                       device_type, backed_up, transports, label,
                       created_at, last_used_at
                FROM webauthn_credentials
                WHERE credential_id = $1
                """,
                credential_id,
            )
        return dict(row) if row else None

    async def create(
        self,
        *,
        credential_id: bytes,
        user_id: int,
        public_key: bytes,
        sign_count: int,
        device_type: str,
        backed_up: bool,
        transports: list[str],
        label: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO webauthn_credentials (
                    credential_id, user_id, public_key, sign_count,
                    device_type, backed_up, transports, label
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (credential_id) DO UPDATE SET
                    public_key = EXCLUDED.public_key,
                    sign_count = EXCLUDED.sign_count,
                    device_type = EXCLUDED.device_type,
                    backed_up = EXCLUDED.backed_up,
                    transports = EXCLUDED.transports,
                    label = EXCLUDED.label
                WHERE webauthn_credentials.user_id = EXCLUDED.user_id
                """,
                credential_id,
                user_id,
                public_key,
                sign_count,
                device_type,
                backed_up,
                transports,
                label,
            )

    async def mark_used(
        self,
        credential_id: bytes,
        *,
        sign_count: int,
        device_type: str,
        backed_up: bool,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webauthn_credentials
                SET sign_count = $2,
                    device_type = $3,
                    backed_up = $4,
                    last_used_at = now()
                WHERE credential_id = $1
                """,
                credential_id,
                sign_count,
                device_type,
                backed_up,
            )
