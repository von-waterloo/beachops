"""Add approvals, callback tokens, audit events, and system state.

Revision ID: 012
Revises: 011
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE approvals (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            actor_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE RESTRICT,
            kind TEXT NOT NULL CHECK (kind IN (
                'plan_execution', 'result_review', 'high_risk',
                'deploy', 'merge', 'prod_db',
                'secrets', 'iam', 'destructive'
            )),
            decision TEXT NOT NULL DEFAULT 'pending' CHECK (decision IN (
                'pending', 'approved', 'rejected', 'expired', 'cancelled'
            )),
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            decided_by BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            reason TEXT,
            UNIQUE (job_id, kind)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX approvals_actor_requested_idx
        ON approvals (actor_id, requested_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE callback_tokens (
            token_digest BYTEA PRIMARY KEY,
            actor_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
            job_id UUID NOT NULL REFERENCES beachops_jobs (id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX callback_tokens_expiry_idx
        ON callback_tokens (expires_at)
        WHERE consumed_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE audit_events (
            id BIGSERIAL PRIMARY KEY,
            actor_id BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            job_id UUID REFERENCES beachops_jobs (id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX audit_events_created_idx
        ON audit_events (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    op.execute(
        """
        CREATE TABLE system_state (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_by BIGINT REFERENCES users (tg_user_id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO system_state (key, value)
        VALUES ('panic', '{"enabled": false}'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_state")
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
    op.execute("DROP INDEX IF EXISTS audit_events_created_idx")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP INDEX IF EXISTS callback_tokens_expiry_idx")
    op.execute("DROP TABLE IF EXISTS callback_tokens")
    op.execute("DROP INDEX IF EXISTS approvals_actor_requested_idx")
    op.execute("DROP TABLE IF EXISTS approvals")

