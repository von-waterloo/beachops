"""Add per-user Cursor model selection.

Revision ID: 003
Revises: 002
Create Date: 2026-06-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS cursor_model_key TEXT NOT NULL DEFAULT 'composer-2.5'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'users_cursor_model_key_check'
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT users_cursor_model_key_check
                CHECK (cursor_model_key IN (
                    'composer-2.5', 'opus-4.6', 'gemini-3.5-flash'
                ));
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cursor_model_key")
