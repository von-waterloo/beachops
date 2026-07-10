"""Replace opus-4.8 with fable-5 in cursor_model_key constraint.

Revision ID: 006
Revises: 005
Create Date: 2026-07-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'fable-5'
        WHERE cursor_model_key = 'opus-4.8'
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


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'opus-4.8'
        WHERE cursor_model_key = 'fable-5'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'opus-4.8', 'sonnet-5', 'gemini-3.5-flash'
        ))
        """
    )
