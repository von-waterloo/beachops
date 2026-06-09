-- Legacy reference. Prefer: alembic upgrade head
-- (initial revision: alembic/versions/001_initial_schema.py)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    tg_user_id BIGINT PRIMARY KEY,
    current_mode TEXT NOT NULL DEFAULT 'ask' CHECK (current_mode IN ('ask', 'plan', 'do')),
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_repos (
    id BIGSERIAL PRIMARY KEY,
    tg_user_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    github_url TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'dev',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tg_user_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_user_repos_user ON user_repos (tg_user_id);

CREATE TABLE IF NOT EXISTS agent_sessions (
    tg_user_id BIGINT PRIMARY KEY REFERENCES users (tg_user_id) ON DELETE CASCADE,
    cursor_agent_id TEXT,
    repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
    active_run_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
);

CREATE INDEX IF NOT EXISTS memory_entries_user_repo_idx
    ON memory_entries (tg_user_id, repo_id, created_at DESC);

CREATE INDEX IF NOT EXISTS memory_entries_embedding_idx
    ON memory_entries USING hnsw (embedding vector_cosine_ops);
