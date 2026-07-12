"""Store encrypted GitHub OAuth tokens per Telegram user.

Revision ID: 016
Revises: 015
Create Date: 2026-07-11
"""

from typing import Sequence, Union

from alembic import op

# Alembic exposes operations dynamically; static analyzers cannot see them.
# pylint: disable=no-member

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_github_tokens (
            tg_user_id BIGINT PRIMARY KEY
                REFERENCES users (tg_user_id) ON DELETE CASCADE,
            access_token_enc TEXT NOT NULL,
            github_login TEXT,
            scopes TEXT NOT NULL DEFAULT 'repo',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_github_tokens")
