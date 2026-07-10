"""Append-only security audit persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg

from beachops.domain.security import AuditEvent
from beachops.services.redaction import redact_text, redact_value


class AuditRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        *,
        actor_id: int | None,
        event_type: str,
        action: str,
        outcome: str,
        job_id: UUID | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        safe_details = redact_value(details or {})
        encoded = json.dumps(safe_details, separators=(",", ":"), sort_keys=True)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_events (
                    actor_id, job_id, event_type, action, outcome, details
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                actor_id,
                job_id,
                redact_text(event_type),
                redact_text(action),
                redact_text(outcome),
                encoded,
            )
        assert row is not None
        return AuditEvent(
            id=row["id"],
            actor_id=row["actor_id"],
            job_id=row["job_id"],
            event_type=row["event_type"],
            action=row["action"],
            outcome=row["outcome"],
            details=_json_object(row["details"]),
            created_at=row["created_at"],
        )


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}

