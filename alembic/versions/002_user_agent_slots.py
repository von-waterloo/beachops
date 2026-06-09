"""Replace agent_sessions with user_agent_slots.

Revision ID: 002
Revises: 001
Create Date: 2026-05-29

"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_agent_slots (
            id BIGSERIAL PRIMARY KEY,
            tg_user_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            cursor_agent_id TEXT,
            repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
            active_run_id TEXT,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_agent_slots_user ON user_agent_slots (tg_user_id)"
    )
    op.execute(
        """
        INSERT INTO user_agent_slots (
            tg_user_id, label, cursor_agent_id, repo_id, active_run_id, is_active
        )
        SELECT
            s.tg_user_id,
            'Основной',
            s.cursor_agent_id,
            s.repo_id,
            s.active_run_id,
            TRUE
        FROM agent_sessions s
        WHERE s.cursor_agent_id IS NOT NULL
           OR s.repo_id IS NOT NULL
           OR s.active_run_id IS NOT NULL
        """
    )
    op.execute("DROP TABLE IF EXISTS agent_sessions")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            tg_user_id BIGINT PRIMARY KEY REFERENCES users (tg_user_id) ON DELETE CASCADE,
            cursor_agent_id TEXT,
            repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
            active_run_id TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO agent_sessions (tg_user_id, cursor_agent_id, repo_id, active_run_id)
        SELECT tg_user_id, cursor_agent_id, repo_id, active_run_id
        FROM user_agent_slots
        WHERE is_active = TRUE
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_user_agent_slots_user")
    op.execute("DROP TABLE IF EXISTS user_agent_slots")
