"""Replace gemini-3.5-flash with grok-4.5 in cursor_model_key constraint.

Revision ID: 008
Revises: 007
Create Date: 2026-07-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'grok-4.5'
        WHERE cursor_model_key = 'gemini-3.5-flash'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'fable-5', 'sonnet-5', 'grok-4.5'
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
        SET cursor_model_key = 'gemini-3.5-flash'
        WHERE cursor_model_key = 'grok-4.5'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'fable-5', 'sonnet-5', 'gemini-3.5-flash'
        ))
        """
    )
