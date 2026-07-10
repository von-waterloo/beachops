"""Ownership-scoped persistence for owner approval requests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from beachops.domain.security import Approval, ApprovalDecision, ApprovalKind, Role
from beachops.services.authz import require_owner
from beachops.services.redaction import redact_text


class ApprovalRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        kind: ApprovalKind,
        expires_at: datetime,
        approval_id: UUID | None = None,
    ) -> Approval | None:
        new_id = approval_id or uuid4()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO approvals (id, job_id, actor_id, kind, expires_at)
                SELECT $3, id, actor_id, $4, $5
                FROM beachops_jobs
                WHERE id = $1 AND actor_id = $2
                RETURNING *
                """,
                job_id,
                actor_id,
                new_id,
                kind.value,
                expires_at,
            )
        return _row_to_approval(row) if row else None

    async def get(self, actor_id: int, approval_id: UUID) -> Approval | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM approvals WHERE id = $1 AND actor_id = $2",
                approval_id,
                actor_id,
            )
        return _row_to_approval(row) if row else None

    async def get_internal(self, approval_id: UUID) -> Approval | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM approvals WHERE id = $1",
                approval_id,
            )
        return _row_to_approval(row) if row else None

    async def list_pending(self, *, limit: int = 100) -> list[Approval]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM approvals
                WHERE decision = 'pending' AND expires_at > now()
                ORDER BY requested_at
                LIMIT $1
                """,
                max(1, min(limit, 200)),
            )
        return [_row_to_approval(row) for row in rows]

    async def get_for_job(
        self,
        actor_id: int,
        job_id: UUID,
        *,
        kind: ApprovalKind,
    ) -> Approval | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM approvals
                WHERE actor_id = $1 AND job_id = $2 AND kind = $3
                """,
                actor_id,
                job_id,
                kind.value,
            )
        return _row_to_approval(row) if row else None

    async def decide(
        self,
        actor_id: int,
        approval_id: UUID,
        *,
        decided_by: int,
        decider_role: Role,
        decision: ApprovalDecision,
        reason: str | None = None,
    ) -> Approval | None:
        require_owner(decider_role)
        if decision not in {ApprovalDecision.APPROVED, ApprovalDecision.REJECTED}:
            raise ValueError("decision must be approved or rejected")
        safe_reason = redact_text(reason) if reason is not None else None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE approvals AS approval
                SET decision = $4,
                    decided_by = $3,
                    decided_at = now(),
                    reason = $5
                FROM users AS approver
                WHERE approval.id = $1
                  AND approval.actor_id = $2
                  AND approval.decision = 'pending'
                  AND approval.expires_at > now()
                  AND approver.tg_user_id = $3
                  AND approver.role = 'owner'
                RETURNING approval.*
                """,
                approval_id,
                actor_id,
                decided_by,
                decision.value,
                safe_reason,
            )
        return _row_to_approval(row) if row else None

    async def expire_pending(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE approvals
                SET decision = 'expired', decided_at = now()
                WHERE decision = 'pending' AND expires_at <= now()
                """
            )
        return int(result.rsplit(" ", 1)[-1])


def _row_to_approval(row: asyncpg.Record) -> Approval:
    return Approval(
        id=row["id"],
        job_id=row["job_id"],
        actor_id=row["actor_id"],
        kind=ApprovalKind(row["kind"]),
        decision=ApprovalDecision(row["decision"]),
        requested_at=row["requested_at"],
        expires_at=row["expires_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        reason=row["reason"],
    )

