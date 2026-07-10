"""Single-use, actor-bound callback token persistence."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg


class CallbackTokenRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def issue(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        action: str,
        ttl_sec: int,
    ) -> str:
        return await self.issue_for_recipient(
            job_owner_id=actor_id,
            recipient_actor_id=actor_id,
            job_id=job_id,
            action=action,
            ttl_sec=ttl_sec,
        )

    async def issue_for_recipient(
        self,
        *,
        job_owner_id: int,
        recipient_actor_id: int,
        job_id: UUID,
        action: str,
        ttl_sec: int,
    ) -> str:
        if not action or len(action) > 100:
            raise ValueError("callback action must contain 1-100 characters")
        if ttl_sec <= 0:
            raise ValueError("callback token TTL must be positive")
        token = secrets.token_urlsafe(32)
        digest = _digest(token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO callback_tokens (
                    token_digest, actor_id, job_id, action, expires_at
                )
                SELECT $4, recipient.tg_user_id, job.id, $5, $6
                FROM beachops_jobs AS job
                JOIN users AS recipient ON recipient.tg_user_id = $3
                WHERE job.id = $1 AND job.actor_id = $2
                RETURNING token_digest
                """,
                job_id,
                job_owner_id,
                recipient_actor_id,
                digest,
                action,
                expires_at,
            )
        if row is None:
            raise LookupError("job not found for actor")
        return token

    async def consume_opaque(
        self,
        token: str,
        *,
        actor_id: int,
        action: str,
    ) -> UUID | None:
        digest = _digest(token)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE callback_tokens
                SET consumed_at = now()
                WHERE token_digest = $1
                  AND actor_id = $2
                  AND action = $3
                  AND consumed_at IS NULL
                  AND expires_at > now()
                RETURNING job_id
                """,
                digest,
                actor_id,
                action,
            )
        return row["job_id"] if row else None

    async def consume(
        self,
        token: str,
        *,
        actor_id: int,
        job_id: UUID,
        action: str,
    ) -> bool:
        digest = _digest(token)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE callback_tokens
                SET consumed_at = now()
                WHERE token_digest = $1
                  AND actor_id = $2
                  AND job_id = $3
                  AND action = $4
                  AND consumed_at IS NULL
                  AND expires_at > now()
                RETURNING token_digest
                """,
                digest,
                actor_id,
                job_id,
                action,
            )
        return row is not None

    async def delete_expired(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM callback_tokens
                WHERE expires_at <= now() OR consumed_at IS NOT NULL
                """
            )
        return int(result.rsplit(" ", 1)[-1])


def token_digest(token: str) -> bytes:
    """Public helper for deterministic tests and operational inspection."""
    return _digest(token)


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()

