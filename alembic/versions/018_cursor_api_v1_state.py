"""Add Cursor API v1 run state, usage, model params, and agent cloud status.

Revision ID: 018
Revises: 017
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE beachops_jobs
            ADD COLUMN IF NOT EXISTS cursor_token_key TEXT,
            ADD COLUMN IF NOT EXISTS cursor_last_event_id TEXT,
            ADD COLUMN IF NOT EXISTS cursor_run_status TEXT,
            ADD COLUMN IF NOT EXISTS input_tokens BIGINT,
            ADD COLUMN IF NOT EXISTS output_tokens BIGINT,
            ADD COLUMN IF NOT EXISTS cache_read_tokens BIGINT,
            ADD COLUMN IF NOT EXISTS cache_write_tokens BIGINT,
            ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS cursor_model_params JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        ALTER TABLE user_agent_slots
            ADD COLUMN IF NOT EXISTS cloud_status TEXT NOT NULL DEFAULT 'unknown',
            ADD COLUMN IF NOT EXISTS last_cloud_sync_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS user_agent_slots_cursor_agent_id_idx
        ON user_agent_slots (cursor_agent_id)
        WHERE cursor_agent_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS user_agent_slots_cursor_agent_id_idx")
    op.execute("ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS last_cloud_sync_at")
    op.execute("ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS cloud_status")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cursor_model_params")
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'fable-5', 'sonnet-5', 'gpt-5.6-terra'
        ))
        """
    )
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS finalized_at")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS cache_write_tokens")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS cache_read_tokens")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS output_tokens")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS input_tokens")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS cursor_run_status")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS cursor_last_event_id")
    op.execute("ALTER TABLE beachops_jobs DROP COLUMN IF EXISTS cursor_token_key")
