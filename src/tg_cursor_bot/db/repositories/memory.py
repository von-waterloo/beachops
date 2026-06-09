"""Memory entries with pgvector."""

from __future__ import annotations

from datetime import datetime

import asyncpg

from tg_cursor_bot.domain.models import MemoryEntry, RunSummary


class MemoryRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(
        self,
        *,
        tg_user_id: int,
        repo_id: int | None,
        kind: str,
        title: str,
        body: str,
        embedding: list[float] | None = None,
        source_prompt: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        pr_url: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
    ) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_entries (
                    tg_user_id, repo_id, kind, title, body, source_prompt,
                    embedding, run_id, mode, pr_url, status, duration_ms
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
                """,
                tg_user_id,
                repo_id,
                kind,
                title,
                body,
                source_prompt,
                embedding,
                run_id,
                mode,
                pr_url,
                status,
                duration_ms,
            )
        assert row is not None
        return int(row["id"])

    async def recall(
        self,
        tg_user_id: int,
        repo_id: int | None,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[MemoryEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, kind, title, body, source_prompt, mode, pr_url, status,
                       duration_ms, created_at, run_id, repo_id
                FROM memory_entries
                WHERE tg_user_id = $1
                  AND embedding IS NOT NULL
                  AND ($2::bigint IS NULL OR repo_id = $2 OR repo_id IS NULL)
                ORDER BY embedding <=> $3
                LIMIT $4
                """,
                tg_user_id,
                repo_id,
                query_embedding,
                limit,
            )
        return [_row_to_entry(row) for row in rows]

    async def search_text(
        self,
        tg_user_id: int,
        repo_id: int | None,
        query: str,
        *,
        limit: int,
    ) -> list[MemoryEntry]:
        pattern = f"%{query}%"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, kind, title, body, source_prompt, mode, pr_url, status,
                       duration_ms, created_at, run_id, repo_id
                FROM memory_entries
                WHERE tg_user_id = $1
                  AND ($2::bigint IS NULL OR repo_id = $2 OR repo_id IS NULL)
                  AND (title ILIKE $3 OR body ILIKE $3)
                ORDER BY created_at DESC
                LIMIT $4
                """,
                tg_user_id,
                repo_id,
                pattern,
                limit,
            )
        return [_row_to_entry(row) for row in rows]

    async def search_semantic(
        self,
        tg_user_id: int,
        repo_id: int | None,
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[MemoryEntry]:
        return await self.recall(
            tg_user_id,
            repo_id,
            query_embedding,
            limit=limit,
        )

    async def list_recent(
        self,
        tg_user_id: int,
        *,
        limit: int,
        repo_id: int | None = None,
    ) -> list[MemoryEntry]:
        async with self._pool.acquire() as conn:
            if repo_id is None:
                rows = await conn.fetch(
                    """
                    SELECT id, kind, title, body, source_prompt, mode, pr_url, status,
                           duration_ms, created_at, run_id, repo_id
                    FROM memory_entries
                    WHERE tg_user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    tg_user_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, kind, title, body, source_prompt, mode, pr_url, status,
                           duration_ms, created_at, run_id, repo_id
                    FROM memory_entries
                    WHERE tg_user_id = $1
                      AND (repo_id = $2 OR repo_id IS NULL)
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    tg_user_id,
                    repo_id,
                    limit,
                )
        return [_row_to_entry(row) for row in rows]

    async def get_by_id(self, tg_user_id: int, entry_id: int) -> MemoryEntry | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, kind, title, body, source_prompt, mode, pr_url, status,
                       duration_ms, created_at, run_id, repo_id
                FROM memory_entries
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                entry_id,
            )
        return _row_to_entry(row) if row else None

    async def list_runs_for_retry(
        self,
        tg_user_id: int,
        *,
        limit: int,
    ) -> list[RunSummary]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, mode, source_prompt, body, pr_url, status, duration_ms,
                       created_at, run_id
                FROM memory_entries
                WHERE tg_user_id = $1 AND kind = 'run'
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tg_user_id,
                limit,
            )
        return [_row_to_run_summary(row) for row in rows]

    async def get_run_by_id(self, tg_user_id: int, entry_id: int) -> RunSummary | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, mode, source_prompt, body, pr_url, status, duration_ms,
                       created_at, run_id
                FROM memory_entries
                WHERE tg_user_id = $1 AND id = $2 AND kind = 'run'
                """,
                tg_user_id,
                entry_id,
            )
        return _row_to_run_summary(row) if row else None


def _format_ts(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _row_to_entry(row: asyncpg.Record) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        source_prompt=row["source_prompt"],
        mode=row["mode"],
        pr_url=row["pr_url"],
        status=row["status"],
        duration_ms=row["duration_ms"],
        created_at=_format_ts(row["created_at"]),
        run_id=row["run_id"],
        repo_id=row["repo_id"],
    )


def _row_to_run_summary(row: asyncpg.Record) -> RunSummary:
    prompt = row["source_prompt"] or row["body"][:80]
    return RunSummary(
        id=row["id"],
        mode=row["mode"] or "ask",
        prompt_summary=prompt,
        result_summary=row["body"],
        pr_url=row["pr_url"],
        status=row["status"] or "unknown",
        duration_ms=row["duration_ms"],
        created_at=_format_ts(row["created_at"]),
        cursor_agent_id=None,
        run_id=row["run_id"],
    )
