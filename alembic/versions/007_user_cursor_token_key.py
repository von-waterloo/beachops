"""Add per-user cursor_token_key (mt / mt2 switch).

Revision ID: 007
Revises: 006
Create Date: 2026-07-09

"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS cursor_token_key TEXT NOT NULL DEFAULT 'mt'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_token_key_check
        CHECK (cursor_token_key IN ('mt', 'mt2'))
        """
    )
    # Токен фиксируется на слоте при первом run: агент Cursor, созданный
    # под одним токеном, нельзя резюмить другим. NULL = ещё не было run.
    op.execute(
        """
        ALTER TABLE user_agent_slots
        ADD COLUMN IF NOT EXISTS cursor_token_key TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE user_agent_slots
        ADD CONSTRAINT user_agent_slots_cursor_token_key_check
        CHECK (cursor_token_key IS NULL OR cursor_token_key IN ('mt', 'mt2'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_agent_slots "
        "DROP CONSTRAINT IF EXISTS user_agent_slots_cursor_token_key_check"
    )
    op.execute("ALTER TABLE user_agent_slots DROP COLUMN IF EXISTS cursor_token_key")
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_token_key_check"
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cursor_token_key")
