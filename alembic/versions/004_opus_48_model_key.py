"""Replace opus-4.6 with opus-4.8 in cursor_model_key constraint.

Revision ID: 004
Revises: 003
Create Date: 2026-06-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'opus-4.8'
        WHERE cursor_model_key = 'opus-4.6'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'opus-4.8', 'gemini-3.5-flash'
        ))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'opus-4.6'
        WHERE cursor_model_key = 'opus-4.8'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'opus-4.6', 'gemini-3.5-flash'
        ))
        """
    )
