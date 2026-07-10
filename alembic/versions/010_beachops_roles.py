"""Add BeachOps RBAC role to users.

Revision ID: 010
Revises: 009
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT")
    op.execute(
        """
        UPDATE users
        SET role = CASE WHEN is_admin THEN 'owner' ELSE 'viewer' END
        WHERE role IS NULL
        """
    )
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'viewer'")
    op.execute("ALTER TABLE users ALTER COLUMN role SET NOT NULL")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_role_check
        CHECK (role IN ('viewer', 'operator', 'owner'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS role")

