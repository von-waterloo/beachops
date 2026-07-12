"""Ownership-scoped persistence for durable BeachOps jobs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from beachops.domain.security import Job, JobKind, JobStatus, RiskLevel
from beachops.services.redaction import redact_text, redact_value


class JobRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        actor_id: int,
        *,
        kind: JobKind,
        risk_level: RiskLevel,
        status: JobStatus = JobStatus.QUEUED,
        repository_url: str | None = None,
        branch: str | None = None,
        summary: str = "",
        payload_ciphertext: str | None = None,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        idempotency_key: str | None = None,
        job_id: UUID | None = None,
        runtime: str = "cloud",
    ) -> Job:
        new_id = job_id or uuid4()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO beachops_jobs (
                    id, actor_id, kind, status, risk_level, repository_url,
                    branch, summary, payload_ciphertext, telegram_chat_id,
                    telegram_message_id, idempotency_key, runtime
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING *
                """,
                new_id,
                actor_id,
                kind.value,
                status.value,
                risk_level.value,
                repository_url,
                branch,
                redact_text(summary),
                payload_ciphertext,
                telegram_chat_id,
                telegram_message_id,
                idempotency_key,
                runtime or "cloud",
            )
        assert row is not None
        return _row_to_job(row)

    async def get(self, actor_id: int, job_id: UUID) -> Job | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM beachops_jobs WHERE id = $1 AND actor_id = $2",
                job_id,
                actor_id,
            )
        return _row_to_job(row) if row else None

    async def get_internal(self, job_id: UUID) -> Job | None:
        """Worker-only lookup; never expose this method through user routes."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM beachops_jobs WHERE id = $1",
                job_id,
            )
        return _row_to_job(row) if row else None

    async def list_for_actor(self, actor_id: int, *, limit: int = 50) -> list[Job]:
        safe_limit = max(1, min(limit, 200))
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_jobs
                WHERE actor_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                actor_id,
                safe_limit,
            )
        return [_row_to_job(row) for row in rows]

    async def list_by_status_internal(
        self,
        statuses: Sequence[JobStatus],
        *,
        limit: int = 500,
    ) -> list[Job]:
        if not statuses:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_jobs
                WHERE status = ANY($1::text[])
                ORDER BY created_at
                LIMIT $2
                """,
                [status.value for status in statuses],
                max(1, min(limit, 1000)),
            )
        return [_row_to_job(row) for row in rows]

    async def list_all_internal(self, *, limit: int = 200) -> list[Job]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_jobs
                ORDER BY created_at DESC
                LIMIT $1
                """,
                max(1, min(limit, 500)),
            )
        return [_row_to_job(row) for row in rows]

    async def transition(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        from_statuses: Sequence[JobStatus],
        to_status: JobStatus,
        event_type: str,
        details: Mapping[str, Any] | None = None,
    ) -> Job | None:
        if not from_statuses:
            raise ValueError("from_statuses cannot be empty")
        encoded_details = json.dumps(
            redact_value(details or {}),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                current_status = await conn.fetchval(
                    """
                    SELECT status
                    FROM beachops_jobs
                    WHERE id = $1 AND actor_id = $2
                    FOR UPDATE
                    """,
                    job_id,
                    actor_id,
                )
                allowed_statuses = {status.value for status in from_statuses}
                if current_status not in allowed_statuses:
                    return None
                row = await conn.fetchrow(
                    """
                    UPDATE beachops_jobs
                    SET status = $3, updated_at = now()
                    WHERE id = $1 AND actor_id = $2
                    RETURNING *
                    """,
                    job_id,
                    actor_id,
                    to_status.value,
                )
                if row is None:
                    return None
                await conn.execute(
                    """
                    INSERT INTO beachops_job_events (
                        job_id, actor_id, event_type, from_status, to_status, details
                    )
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """,
                    job_id,
                    actor_id,
                    event_type,
                    current_status,
                    to_status.value,
                    encoded_details,
                )
        return _row_to_job(row)

    async def append_event(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        event_type: str,
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        encoded = json.dumps(
            redact_value(details or {}),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO beachops_job_events (job_id, actor_id, event_type, details)
                SELECT id, actor_id, $3, $4::jsonb
                FROM beachops_jobs
                WHERE id = $1 AND actor_id = $2
                RETURNING id
                """,
                job_id,
                actor_id,
                event_type,
                encoded,
            )
        return row is not None

    async def add_artifact(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        artifact_kind: str,
        uri: str,
        sha256: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> int | None:
        encoded = json.dumps(
            redact_value(metadata or {}),
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO beachops_artifacts (
                    job_id, artifact_kind, uri, sha256, metadata
                )
                SELECT id, $3, $4, $5, $6::jsonb
                FROM beachops_jobs
                WHERE id = $1 AND actor_id = $2
                RETURNING id
                """,
                job_id,
                actor_id,
                artifact_kind,
                redact_text(uri),
                sha256,
                encoded,
            )
        return int(row["id"]) if row else None

    async def list_queued_for_actor(self, actor_id: int) -> list[Job]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM beachops_jobs
                WHERE actor_id = $1
                  AND status = ANY($2::text[])
                ORDER BY created_at
                """,
                actor_id,
                [
                    JobStatus.QUEUED.value,
                    JobStatus.APPROVED.value,
                    JobStatus.REVISION_REQUESTED.value,
                ],
            )
        return [_row_to_job(row) for row in rows]

    async def count_pending_for_actor(self, actor_id: int) -> int:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT COUNT(*) FROM beachops_jobs
                WHERE actor_id = $1
                  AND status = ANY($2::text[])
                """,
                actor_id,
                [
                    JobStatus.QUEUED.value,
                    JobStatus.APPROVED.value,
                    JobStatus.REVISION_REQUESTED.value,
                    JobStatus.RUNNING.value,
                    JobStatus.PLANNING.value,
                ],
            )
        return int(value or 0)

    async def queue_position(self, actor_id: int, job_id: UUID) -> int:
        """1-based position among queued jobs for this actor (0 if not queued)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id FROM beachops_jobs
                WHERE actor_id = $1
                  AND status = ANY($2::text[])
                ORDER BY created_at
                """,
                actor_id,
                [
                    JobStatus.QUEUED.value,
                    JobStatus.APPROVED.value,
                    JobStatus.REVISION_REQUESTED.value,
                ],
            )
        for index, row in enumerate(rows, start=1):
            if row["id"] == job_id:
                return index
        return 0

    async def cancel_queued_for_actor(self, actor_id: int) -> int:
        jobs = await self.list_queued_for_actor(actor_id)
        cancelled = 0
        for job in jobs:
            updated = await self.transition(
                actor_id,
                job.id,
                from_statuses=[job.status],
                to_status=JobStatus.CANCELLED,
                event_type="user.cancel_queued",
            )
            if updated is not None:
                cancelled += 1
        return cancelled

    async def latest_active_for_actor(self, actor_id: int) -> Job | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM beachops_jobs
                WHERE actor_id = $1
                  AND status = ANY($2::text[])
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                actor_id,
                [JobStatus.RUNNING.value, JobStatus.PLANNING.value],
            )
        return _row_to_job(row) if row else None

    async def claim_for_worker(
        self,
        worker_node_id: UUID,
        *,
        runtime: str = "windows",
    ) -> Job | None:
        """Atomically claim the oldest queued job for a Windows worker."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id FROM beachops_jobs
                    WHERE runtime = $1
                      AND status = ANY($2::text[])
                      AND (worker_node_id IS NULL OR worker_node_id = $3)
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    runtime,
                    [
                        JobStatus.QUEUED.value,
                        JobStatus.APPROVED.value,
                        JobStatus.REVISION_REQUESTED.value,
                    ],
                    worker_node_id,
                )
                if row is None:
                    return None
                claimed = await conn.fetchrow(
                    """
                    UPDATE beachops_jobs
                    SET status = $2,
                        worker_node_id = $3,
                        attempt = attempt + 1,
                        started_at = COALESCE(started_at, now()),
                        updated_at = now()
                    WHERE id = $1
                    RETURNING *
                    """,
                    row["id"],
                    JobStatus.RUNNING.value,
                    worker_node_id,
                )
        return _row_to_job(claimed) if claimed else None

    async def set_runtime(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        cursor_agent_id: str | None = None,
        cursor_run_id: str | None = None,
        cursor_token_key: str | None = None,
        cursor_last_event_id: str | None = None,
        cursor_run_status: str | None = None,
        telegram_message_id: int | None = None,
        telegram_chat_id: int | None = None,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE beachops_jobs
                SET cursor_agent_id = COALESCE($3, cursor_agent_id),
                    cursor_run_id = COALESCE($4, cursor_run_id),
                    cursor_token_key = COALESCE($5, cursor_token_key),
                    cursor_last_event_id = COALESCE($6, cursor_last_event_id),
                    cursor_run_status = COALESCE($7, cursor_run_status),
                    telegram_message_id = COALESCE($8, telegram_message_id),
                    telegram_chat_id = COALESCE($9, telegram_chat_id),
                    updated_at = now()
                WHERE id = $1 AND actor_id = $2
                RETURNING id
                """,
                job_id,
                actor_id,
                cursor_agent_id,
                cursor_run_id,
                cursor_token_key,
                cursor_last_event_id,
                cursor_run_status,
                telegram_message_id,
                telegram_chat_id,
            )
        return row is not None

    async def set_result(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        pr_url: str | None,
        total_tokens: int | None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE beachops_jobs
                SET pr_url = $3,
                    total_tokens = $4,
                    input_tokens = COALESCE($5, input_tokens),
                    output_tokens = COALESCE($6, output_tokens),
                    cache_read_tokens = COALESCE($7, cache_read_tokens),
                    cache_write_tokens = COALESCE($8, cache_write_tokens),
                    updated_at = now()
                WHERE id = $1 AND actor_id = $2
                RETURNING id
                """,
                job_id,
                actor_id,
                redact_text(pr_url) if pr_url else None,
                total_tokens,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
            )
        return row is not None

    async def mark_finalized(self, actor_id: int, job_id: UUID) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE beachops_jobs
                SET finalized_at = COALESCE(finalized_at, now()),
                    finished_at = COALESCE(finished_at, now()),
                    updated_at = now()
                WHERE id = $1 AND actor_id = $2 AND finalized_at IS NULL
                RETURNING id
                """,
                job_id,
                actor_id,
            )
        return row is not None

    async def list_artifacts(
        self,
        actor_id: int,
        job_id: UUID,
    ) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.id, a.artifact_kind, a.uri, a.sha256, a.metadata, a.created_at
                FROM beachops_artifacts a
                JOIN beachops_jobs j ON j.id = a.job_id
                WHERE a.job_id = $1 AND j.actor_id = $2
                ORDER BY a.id
                """,
                job_id,
                actor_id,
            )
        return [dict(row) for row in rows]

    async def list_events(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, from_status, to_status, details, created_at
                FROM beachops_job_events
                WHERE job_id = $1 AND actor_id = $2
                ORDER BY id
                LIMIT $3
                """,
                job_id,
                actor_id,
                max(1, min(limit, 500)),
            )
        return [dict(row) for row in rows]


def _row_to_job(row: asyncpg.Record) -> Job:
    keys = row.keys()
    return Job(
        id=row["id"],
        actor_id=row["actor_id"],
        kind=JobKind(row["kind"]),
        status=JobStatus(row["status"]),
        risk_level=RiskLevel(row["risk_level"]),
        repository_url=row["repository_url"],
        branch=row["branch"],
        summary=row["summary"],
        payload_ciphertext=row["payload_ciphertext"],
        cursor_agent_id=row["cursor_agent_id"],
        cursor_run_id=row["cursor_run_id"],
        cursor_token_key=row["cursor_token_key"] if "cursor_token_key" in keys else None,
        cursor_last_event_id=(
            row["cursor_last_event_id"] if "cursor_last_event_id" in keys else None
        ),
        cursor_run_status=row["cursor_run_status"] if "cursor_run_status" in keys else None,
        pr_url=row["pr_url"],
        total_tokens=row["total_tokens"],
        input_tokens=row["input_tokens"] if "input_tokens" in keys else None,
        output_tokens=row["output_tokens"] if "output_tokens" in keys else None,
        cache_read_tokens=row["cache_read_tokens"] if "cache_read_tokens" in keys else None,
        cache_write_tokens=(
            row["cache_write_tokens"] if "cache_write_tokens" in keys else None
        ),
        telegram_chat_id=row["telegram_chat_id"],
        telegram_message_id=row["telegram_message_id"],
        idempotency_key=row["idempotency_key"],
        runtime=row["runtime"] if "runtime" in keys else "cloud",
        worker_node_id=row["worker_node_id"] if "worker_node_id" in keys else None,
        attempt=int(row["attempt"]) if "attempt" in keys and row["attempt"] is not None else 0,
        telegram_updated=bool(row["telegram_updated"]) if "telegram_updated" in keys else False,
        started_at=row["started_at"] if "started_at" in keys else None,
        finished_at=row["finished_at"] if "finished_at" in keys else None,
        finalized_at=row["finalized_at"] if "finalized_at" in keys else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

