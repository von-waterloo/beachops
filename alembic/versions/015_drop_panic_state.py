"""Remove obsolete panic system_state key.

Revision ID: 015
Revises: 014
Create Date: 2026-07-11
"""

from typing import Sequence, Union

from alembic import op

# Alembic exposes operations dynamically; static analyzers cannot see them.
# pylint: disable=no-member

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM system_state WHERE key = 'panic'")


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO system_state (key, value)
        VALUES ('panic', '{"enabled": false}'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )
