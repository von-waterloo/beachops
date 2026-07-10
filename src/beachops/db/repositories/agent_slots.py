"""Named Cursor agent slots per user."""

from __future__ import annotations

import asyncpg

from beachops.domain.models import AgentSlot


class AgentSlotRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_slots(self, tg_user_id: int) -> list[AgentSlot]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.id, s.tg_user_id, s.label, s.cursor_agent_id,
                       s.repo_id, s.active_run_id, s.is_active,
                       s.cursor_token_key, s.runtime, s.local_path,
                       s.preferred_worker_id, r.alias AS repo_alias
                FROM user_agent_slots s
                LEFT JOIN user_repos r ON r.id = s.repo_id
                WHERE s.tg_user_id = $1
                ORDER BY s.id
                """,
                tg_user_id,
            )
        return [_row_to_slot(row) for row in rows]

    async def get_by_id(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT s.id, s.tg_user_id, s.label, s.cursor_agent_id,
                       s.repo_id, s.active_run_id, s.is_active,
                       s.cursor_token_key, s.runtime, s.local_path,
                       s.preferred_worker_id, r.alias AS repo_alias
                FROM user_agent_slots s
                LEFT JOIN user_repos r ON r.id = s.repo_id
                WHERE s.tg_user_id = $1 AND s.id = $2
                """,
                tg_user_id,
                slot_id,
            )
        return _row_to_slot(row) if row else None

    async def get_active(self, tg_user_id: int) -> AgentSlot | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT s.id, s.tg_user_id, s.label, s.cursor_agent_id,
                       s.repo_id, s.active_run_id, s.is_active,
                       s.cursor_token_key, s.runtime, s.local_path,
                       s.preferred_worker_id, r.alias AS repo_alias
                FROM user_agent_slots s
                LEFT JOIN user_repos r ON r.id = s.repo_id
                WHERE s.tg_user_id = $1 AND s.is_active = TRUE
                LIMIT 1
                """,
                tg_user_id,
            )
        return _row_to_slot(row) if row else None

    async def count_slots(self, tg_user_id: int) -> int:
        async with self._pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "SELECT COUNT(*) FROM user_agent_slots WHERE tg_user_id = $1",
                    tg_user_id,
                )
                or 0
            )

    async def create_slot(
        self,
        tg_user_id: int,
        *,
        label: str,
        repo_id: int | None,
        make_active: bool,
    ) -> AgentSlot:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if make_active:
                    await conn.execute(
                        "UPDATE user_agent_slots SET is_active = FALSE WHERE tg_user_id = $1",
                        tg_user_id,
                    )
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_agent_slots (
                        tg_user_id, label, repo_id, is_active
                    )
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    tg_user_id,
                    label,
                    repo_id,
                    make_active,
                )
        assert row is not None
        slot = await self.get_by_id(tg_user_id, row["id"])
        assert slot is not None
        return slot

    async def set_active(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM user_agent_slots
                    WHERE tg_user_id = $1 AND id = $2
                    """,
                    tg_user_id,
                    slot_id,
                )
                if not exists:
                    return None
                await conn.execute(
                    "UPDATE user_agent_slots SET is_active = FALSE WHERE tg_user_id = $1",
                    tg_user_id,
                )
                await conn.execute(
                    """
                    UPDATE user_agent_slots
                    SET is_active = TRUE, updated_at = now()
                    WHERE tg_user_id = $1 AND id = $2
                    """,
                    tg_user_id,
                    slot_id,
                )
        return await self.get_by_id(tg_user_id, slot_id)

    async def update_cursor_agent(
        self,
        slot_id: int,
        cursor_agent_id: str,
        *,
        token_key: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_agent_slots
                SET cursor_agent_id = $2,
                    cursor_token_key = COALESCE($3, cursor_token_key),
                    updated_at = now()
                WHERE id = $1
                """,
                slot_id,
                cursor_agent_id,
                token_key,
            )

    async def set_active_run(self, slot_id: int, run_id: str | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_agent_slots
                SET active_run_id = $2, updated_at = now()
                WHERE id = $1
                """,
                slot_id,
                run_id,
            )

    async def clear_all_active_runs(self) -> None:
        """Drop stale run bindings after bot restart (single-instance deployment)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_agent_slots SET active_run_id = NULL WHERE active_run_id IS NOT NULL"
            )

    async def update_repo_id(self, slot_id: int, repo_id: int | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_agent_slots
                SET repo_id = $2, updated_at = now()
                WHERE id = $1
                """,
                slot_id,
                repo_id,
            )

    async def rebind_repo(self, slot_id: int, repo_id: int) -> None:
        """Point slot at a different repo; drop Cursor agent (repo-bound)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_agent_slots
                SET repo_id = $2,
                    cursor_agent_id = NULL,
                    cursor_token_key = NULL,
                    active_run_id = NULL,
                    updated_at = now()
                WHERE id = $1
                """,
                slot_id,
                repo_id,
            )

    async def update_label(self, tg_user_id: int, slot_id: int, label: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE user_agent_slots
                SET label = $3, updated_at = now()
                WHERE id = $1 AND tg_user_id = $2
                """,
                slot_id,
                tg_user_id,
                label,
            )
        return result.endswith("1")

    async def update_runtime_config(
        self,
        tg_user_id: int,
        slot_id: int,
        *,
        runtime: str | None = None,
        local_path: str | None = None,
        clear_local_path: bool = False,
        preferred_worker_id: str | None = None,
        clear_preferred_worker: bool = False,
    ) -> AgentSlot | None:
        """Patch runtime / Windows path / preferred worker for a slot."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT runtime, local_path, preferred_worker_id
                FROM user_agent_slots
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                slot_id,
            )
            if row is None:
                return None

            next_runtime = runtime if runtime is not None else row["runtime"]
            if clear_local_path:
                next_path = None
            elif local_path is not None:
                next_path = local_path.strip() or None
            else:
                next_path = row["local_path"]

            if clear_preferred_worker:
                next_worker = None
            elif preferred_worker_id is not None:
                next_worker = preferred_worker_id.strip() or None
            else:
                next_worker = row["preferred_worker_id"]

            await conn.execute(
                """
                UPDATE user_agent_slots
                SET runtime = COALESCE($3, runtime),
                    local_path = $4,
                    preferred_worker_id = $5::uuid,
                    updated_at = now()
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                slot_id,
                next_runtime,
                next_path,
                next_worker,
            )
        return await self.get_by_id(tg_user_id, slot_id)

    async def delete_slot(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        """Delete slot; activate another if the deleted one was active."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                count = int(
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM user_agent_slots WHERE tg_user_id = $1",
                        tg_user_id,
                    )
                    or 0
                )
                if count <= 1:
                    return None

                row = await conn.fetchrow(
                    """
                    SELECT id, is_active
                    FROM user_agent_slots
                    WHERE tg_user_id = $1 AND id = $2
                    """,
                    tg_user_id,
                    slot_id,
                )
                if row is None:
                    return None

                was_active = bool(row["is_active"])
                await conn.execute(
                    "DELETE FROM user_agent_slots WHERE tg_user_id = $1 AND id = $2",
                    tg_user_id,
                    slot_id,
                )

                if was_active:
                    await conn.execute(
                        "UPDATE user_agent_slots SET is_active = FALSE WHERE tg_user_id = $1",
                        tg_user_id,
                    )
                    next_id = await conn.fetchval(
                        """
                        SELECT id FROM user_agent_slots
                        WHERE tg_user_id = $1
                        ORDER BY id
                        LIMIT 1
                        """,
                        tg_user_id,
                    )
                    if next_id is not None:
                        await conn.execute(
                            """
                            UPDATE user_agent_slots
                            SET is_active = TRUE, updated_at = now()
                            WHERE id = $1
                            """,
                            next_id,
                        )

        return await self.get_active(tg_user_id)


def _row_to_slot(row: asyncpg.Record) -> AgentSlot:
    keys = row.keys()
    preferred = row["preferred_worker_id"] if "preferred_worker_id" in keys else None
    return AgentSlot(
        id=row["id"],
        tg_user_id=row["tg_user_id"],
        label=row["label"],
        cursor_agent_id=row["cursor_agent_id"],
        repo_id=row["repo_id"],
        active_run_id=row["active_run_id"],
        is_active=bool(row["is_active"]),
        repo_alias=row.get("repo_alias"),
        cursor_token_key=row.get("cursor_token_key"),
        runtime=row["runtime"] if "runtime" in keys and row["runtime"] else "cloud",
        local_path=row["local_path"] if "local_path" in keys else None,
        preferred_worker_id=str(preferred) if preferred is not None else None,
    )
