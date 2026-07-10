"""Replace grok-4.5 with gpt-5.6-terra in cursor_model_key constraint.

Revision ID: 009
Revises: 008
Create Date: 2026-07-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_cursor_model_key_check"
    )
    op.execute(
        """
        UPDATE users
        SET cursor_model_key = 'gpt-5.6-terra'
        WHERE cursor_model_key = 'grok-4.5'
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_cursor_model_key_check
        CHECK (cursor_model_key IN (
            'composer-2.5', 'fable-5', 'sonnet-5', 'gpt-5.6-terra'
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
        SET cursor_model_key = 'grok-4.5'
        WHERE cursor_model_key = 'gpt-5.6-terra'
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
