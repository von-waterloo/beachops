"""Repositories for run events and notification outbox."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from beachops.services.redaction import redact_value


class RunEventRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        *,
        job_id: UUID,
        actor_id: int | None,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        sequence: int = 0,
    ) -> int | None:
        encoded = json.dumps(
            redact_value(payload or {}),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO beachops_run_events (
                        job_id, actor_id, event_type, sequence, payload, idempotency_key
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    RETURNING id
                    """,
                    job_id,
                    actor_id,
                    event_type,
                    sequence,
                    encoded,
                    idempotency_key,
                )
            except asyncpg.UniqueViolationError:
                return None
        return int(row["id"]) if row else None

    async def list_for_job(
        self,
        job_id: UUID,
        *,
        after_id: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_id, actor_id, event_type, sequence, payload, created_at
                FROM beachops_run_events
                WHERE job_id = $1 AND id > $2
                ORDER BY id
                LIMIT $3
                """,
                job_id,
                after_id,
                max(1, min(limit, 500)),
            )
        return [dict(row) for row in rows]


class NotificationOutboxRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def enqueue(
        self,
        *,
        job_id: UUID,
        actor_id: int,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> int | None:
        encoded = json.dumps(
            redact_value(dict(payload)),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO beachops_notification_outbox (
                        job_id, actor_id, kind, telegram_chat_id, telegram_message_id,
                        payload, idempotency_key
                    )
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                    RETURNING id
                    """,
                    job_id,
                    actor_id,
                    kind,
                    telegram_chat_id,
                    telegram_message_id,
                    encoded,
                    idempotency_key,
                )
            except asyncpg.UniqueViolationError:
                return None
        return int(row["id"]) if row else None

    async def claim_pending(self, *, limit: int = 20) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM beachops_notification_outbox
                    WHERE status = 'pending'
                      AND next_attempt_at <= now()
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                    """,
                    max(1, min(limit, 100)),
                )
                if not rows:
                    return []
                ids = [row["id"] for row in rows]
                await conn.execute(
                    """
                    UPDATE beachops_notification_outbox
                    SET attempts = attempts + 1,
                        updated_at = now()
                    WHERE id = ANY($1::bigint[])
                    """,
                    ids,
                )
        return [dict(row) for row in rows]

    async def mark_sent(self, outbox_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE beachops_notification_outbox
                SET status = 'sent', updated_at = now(), last_error = NULL
                WHERE id = $1
                """,
                outbox_id,
            )

    async def mark_failed(
        self,
        outbox_id: int,
        *,
        error: str,
        retry_in_sec: int = 15,
        give_up_after: int = 12,
    ) -> None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT attempts FROM beachops_notification_outbox WHERE id = $1",
                outbox_id,
            )
            attempts = int(row["attempts"]) if row else 0
            if attempts >= give_up_after:
                await conn.execute(
                    """
                    UPDATE beachops_notification_outbox
                    SET status = 'failed', last_error = $2, updated_at = now()
                    WHERE id = $1
                    """,
                    outbox_id,
                    error[:1000],
                )
            else:
                nxt = datetime.now(timezone.utc) + timedelta(seconds=retry_in_sec)
                await conn.execute(
                    """
                    UPDATE beachops_notification_outbox
                    SET status = 'pending',
                        last_error = $2,
                        next_attempt_at = $3,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    outbox_id,
                    error[:1000],
                    nxt,
                )


class WorkerNodeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def register(
        self,
        *,
        hostname: str,
        token_hash: str,
        capabilities: Mapping[str, Any] | None = None,
        platform: str = "windows",
        enrolled_by: int | None = None,
        node_id: UUID | None = None,
    ) -> dict[str, Any]:
        new_id = node_id or uuid4()
        encoded = json.dumps(
            dict(capabilities or {}),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO beachops_worker_nodes (
                    id, hostname, platform, capabilities, status, token_hash,
                    last_heartbeat_at, enrolled_by, updated_at
                )
                VALUES ($1, $2, $3, $4::jsonb, 'online', $5, now(), $6, now())
                RETURNING *
                """,
                new_id,
                hostname,
                platform,
                encoded,
                token_hash,
                enrolled_by,
            )
        assert row is not None
        return dict(row)

    async def upsert_heartbeat(
        self,
        node_id: UUID,
        *,
        hostname: str,
        capabilities: Mapping[str, Any],
        token_hash: str,
        platform: str = "windows",
    ) -> dict[str, Any]:
        encoded = json.dumps(dict(capabilities), separators=(",", ":"), sort_keys=True)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO beachops_worker_nodes (
                    id, hostname, platform, capabilities, status, token_hash,
                    last_heartbeat_at, updated_at
                )
                VALUES ($1, $2, $3, $4::jsonb, 'online', $5, now(), now())
                ON CONFLICT (id) DO UPDATE SET
                    hostname = EXCLUDED.hostname,
                    capabilities = EXCLUDED.capabilities,
                    status = 'online',
                    last_heartbeat_at = now(),
                    updated_at = now()
                RETURNING *
                """,
                node_id,
                hostname,
                platform,
                encoded,
                token_hash,
            )
        assert row is not None
        return dict(row)

    async def list_all(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_worker_nodes
                ORDER BY last_heartbeat_at DESC NULLS LAST, created_at DESC
                """
            )
        return [dict(row) for row in rows]

    async def list_online(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_worker_nodes
                WHERE status = 'online'
                ORDER BY last_heartbeat_at DESC NULLS LAST
                """
            )
        return [dict(row) for row in rows]

    async def get(self, node_id: UUID) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM beachops_worker_nodes WHERE id = $1",
                node_id,
            )
        return dict(row) if row else None

    async def get_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM beachops_worker_nodes WHERE token_hash = $1",
                token_hash,
            )
        return dict(row) if row else None
