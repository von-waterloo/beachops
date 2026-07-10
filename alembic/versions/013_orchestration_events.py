"""Add orchestration events, notification outbox, and worker nodes.

Revision ID: 013
Revises: 012
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE beachops_jobs
            ADD COLUMN IF NOT EXISTS runtime TEXT NOT NULL DEFAULT 'cloud',
            ADD COLUMN IF NOT EXISTS worker_node_id UUID,
            ADD COLUMN IF NOT EXISTS attempt INT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS telegram_updated BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS beachops_jobs_actor_status_idx
        ON beachops_jobs (actor_id, status, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS beachops_run_events (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            actor_id BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            sequence INT NOT NULL DEFAULT 0,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS beachops_run_events_idem_idx
        ON beachops_run_events (job_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS beachops_run_events_job_seq_idx
        ON beachops_run_events (job_id, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS beachops_notification_outbox (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            actor_id BIGINT NOT NULL,
            kind TEXT NOT NULL,
            telegram_chat_id BIGINT,
            telegram_message_id BIGINT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'failed', 'cancelled')),
            attempts INT NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_error TEXT,
            idempotency_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS beachops_notification_outbox_idem_idx
        ON beachops_notification_outbox (idempotency_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS beachops_notification_outbox_pending_idx
        ON beachops_notification_outbox (status, next_attempt_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS beachops_worker_nodes (
            id UUID PRIMARY KEY,
            hostname TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'windows',
            capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'offline'
                CHECK (status IN ('online', 'offline', 'draining')),
            token_hash TEXT NOT NULL,
            last_heartbeat_at TIMESTAMPTZ,
            enrolled_by BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        ALTER TABLE user_agent_slots
            ADD COLUMN IF NOT EXISTS runtime TEXT NOT NULL DEFAULT 'cloud',
            ADD COLUMN IF NOT EXISTS local_path TEXT,
            ADD COLUMN IF NOT EXISTS preferred_worker_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE user_repos
            ADD COLUMN IF NOT EXISTS local_path TEXT
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_repos DROP COLUMN IF EXISTS local_path")
    op.execute(
        "ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS preferred_worker_id"
    )
    op.execute("ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS local_path")
    op.execute("ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS runtime")
    op.execute("DROP TABLE IF EXISTS beachops_worker_nodes")
    op.execute("DROP INDEX IF EXISTS beachops_notification_outbox_pending_idx")
    op.execute("DROP INDEX IF EXISTS beachops_notification_outbox_idem_idx")
    op.execute("DROP TABLE IF EXISTS beachops_notification_outbox")
    op.execute("DROP INDEX IF EXISTS beachops_run_events_job_seq_idx")
    op.execute("DROP INDEX IF EXISTS beachops_run_events_idem_idx")
    op.execute("DROP TABLE IF EXISTS beachops_run_events")
    op.execute("DROP INDEX IF EXISTS beachops_jobs_actor_status_idx")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS telegram_updated")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS finished_at")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS started_at")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS attempt")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS worker_node_id")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS runtime")
