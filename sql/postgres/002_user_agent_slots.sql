-- Reference SQL for migration 002 (applied via alembic upgrade head).
-- See alembic/versions/002_user_agent_slots.py

CREATE TABLE IF NOT EXISTS user_agent_slots (
    id BIGSERIAL PRIMARY KEY,
    tg_user_id BIGINT NOT NULL REFERENCES users (tg_user_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    cursor_agent_id TEXT,
    repo_id BIGINT REFERENCES user_repos (id) ON DELETE SET NULL,
    active_run_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_agent_slots_user ON user_agent_slots (tg_user_id);

-- Data migration from agent_sessions (run once before DROP):
-- INSERT INTO user_agent_slots (...) SELECT ... FROM agent_sessions;

DROP TABLE IF EXISTS agent_sessions;
