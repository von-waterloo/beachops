"""Initial schema (users, repos, sessions, memory + pgvector).

Revision ID: 001
Revises:
Create Date: 2026-05-29

"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            tg_user_id BIGINT PRIMARY KEY,
            current_mode TEXT NOT NULL DEFAULT 'ask'
                CHECK (current_mode IN ('ask', 'plan', 'do')),
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_repos (
            id BIGSERIAL PRIMARY KEY,
            tg_user_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            github_url TEXT NOT NULL,
            default_branch TEXT NOT NULL DEFAULT 'dev',
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tg_user_id, alias)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_repos_user ON user_repos (tg_user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            tg_user_id BIGINT PRIMARY KEY REFERENCES users (tg_user_id) ON DELETE CASCADE,
            cursor_agent_id TEXT,
            repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
            active_run_id TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_entries (
            id BIGSERIAL PRIMARY KEY,
            tg_user_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
            repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
            kind TEXT NOT NULL CHECK (kind IN ('run', 'note')),
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_prompt TEXT,
            embedding vector(1536),
            run_id TEXT,
            mode TEXT,
            pr_url TEXT,
            status TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS memory_entries_user_repo_idx
            ON memory_entries (tg_user_id, repo_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS memory_entries_embedding_idx
            ON memory_entries USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_entries_embedding_idx")
    op.execute("DROP INDEX IF EXISTS memory_entries_user_repo_idx")
    op.execute("DROP TABLE IF EXISTS memory_entries")
    op.execute("DROP TABLE IF EXISTS agent_sessions")
    op.execute("DROP INDEX IF EXISTS idx_user_repos_user")
    op.execute("DROP TABLE IF EXISTS user_repos")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP EXTENSION IF EXISTS vector")
