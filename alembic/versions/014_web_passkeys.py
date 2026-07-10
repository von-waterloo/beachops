"""Add WebAuthn passkeys for browser authentication.

Revision ID: 014
Revises: 013
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

# Alembic exposes operations dynamically; static analyzers cannot see them.
# pylint: disable=no-member

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webauthn_credentials (
            credential_id BYTEA PRIMARY KEY,
            user_id BIGINT NOT NULL
                REFERENCES users (tg_user_id) ON DELETE CASCADE,
            public_key BYTEA NOT NULL,
            sign_count BIGINT NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
            device_type TEXT NOT NULL,
            backed_up BOOLEAN NOT NULL DEFAULT FALSE,
            transports TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            label TEXT NOT NULL DEFAULT 'Passkey',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS webauthn_credentials_user_idx
        ON webauthn_credentials (user_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS webauthn_credentials_user_idx")
    op.execute("DROP TABLE IF EXISTS webauthn_credentials")
