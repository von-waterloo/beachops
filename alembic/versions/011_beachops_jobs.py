"""Add durable BeachOps jobs, events, and artifacts.

Revision ID: 011
Revises: 010
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE beachops_jobs (
            id UUID PRIMARY KEY,
            actor_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE RESTRICT,
            kind TEXT NOT NULL CHECK (kind IN (
                'read', 'plan', 'change', 'raw_shell', 'deploy', 'merge',
                'prod_db', 'secrets', 'iam', 'delete'
            )),
            status TEXT NOT NULL CHECK (status IN (
                'draft', 'queued', 'planning', 'awaiting_approval', 'approved',
                'running', 'review_required', 'revision_requested', 'paused',
                'accepted', 'rejected', 'succeeded', 'failed', 'cancelled', 'blocked'
            )),
            risk_level TEXT NOT NULL CHECK (risk_level IN (
                'low', 'medium', 'high', 'blocked'
            )),
            repository_url TEXT,
            branch TEXT,
            summary TEXT NOT NULL DEFAULT '',
            payload_ciphertext TEXT,
            cursor_agent_id TEXT,
            cursor_run_id TEXT,
            pr_url TEXT,
            total_tokens BIGINT,
            telegram_chat_id BIGINT,
            telegram_message_id BIGINT,
            idempotency_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX beachops_jobs_actor_created_idx
        ON beachops_jobs (actor_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX beachops_jobs_actor_idempotency_idx
        ON beachops_jobs (actor_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE beachops_job_events (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            actor_id BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX beachops_job_events_job_created_idx
        ON beachops_job_events (job_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE beachops_artifacts (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            artifact_kind TEXT NOT NULL,
            uri TEXT NOT NULL,
            sha256 TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX beachops_artifacts_job_idx
        ON beachops_artifacts (job_id, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS beachops_artifacts_job_idx")
    op.execute("DROP TABLE IF EXISTS beachops_artifacts")
    op.execute("DROP INDEX IF EXISTS beachops_job_events_job_created_idx")
    op.execute("DROP TABLE IF EXISTS beachops_job_events")
    op.execute("DROP INDEX IF EXISTS beachops_jobs_actor_created_idx")
    op.execute("DROP INDEX IF EXISTS beachops_jobs_actor_idempotency_idx")
    op.execute("DROP TABLE IF EXISTS beachops_jobs")

