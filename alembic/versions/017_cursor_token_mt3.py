"""Allow cursor_token_key value mt3 (third Cursor API key).

Revision ID: 017
Revises: 016
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_token_key_check"
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_token_key_check
        CHECK (cursor_token_key IN ('mt', 'mt2', 'mt3'))
        """
    )
    op.execute(
        "ALTER TABLE user_agent_slots "
        "DROP CONSTRAINT IF EXISTS user_agent_slots_cursor_token_key_check"
    )
    op.execute(
        """
        ALTER TABLE user_agent_slots
        ADD CONSTRAINT user_agent_slots_cursor_token_key_check
        CHECK (cursor_token_key IS NULL OR cursor_token_key IN ('mt', 'mt2', 'mt3'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users SET cursor_token_key = 'mt'
        WHERE cursor_token_key = 'mt3'
        """
    )
    op.execute(
        """
        UPDATE user_agent_slots SET cursor_token_key = NULL
        WHERE cursor_token_key = 'mt3'
        """
    )
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_token_key_check"
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_token_key_check
        CHECK (cursor_token_key IN ('mt', 'mt2'))
        """
    )
    op.execute(
        "ALTER TABLE user_agent_slots "
        "DROP CONSTRAINT IF EXISTS user_agent_slots_cursor_token_key_check"
    )
    op.execute(
        """
        ALTER TABLE user_agent_slots
        ADD CONSTRAINT user_agent_slots_cursor_token_key_check
        CHECK (cursor_token_key IS NULL OR cursor_token_key IN ('mt', 'mt2'))
        """
    )
