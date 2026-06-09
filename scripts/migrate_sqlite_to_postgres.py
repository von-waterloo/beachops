#!/usr/bin/env python3
"""Import legacy SQLite bot.db into PostgreSQL (optional one-time migration)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
from pathlib import Path

import asyncpg
from openai import AsyncOpenAI
from pgvector.asyncpg import register_vector


async def _embed(client: AsyncOpenAI, model: str, text: str) -> list[float] | None:
    chunk = text.strip()[:8000]
    if not chunk:
        return None
    try:
        response = await client.embeddings.create(model=model, input=chunk)
    except Exception:
        return None
    return list(response.data[0].embedding)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def migrate(*, sqlite_path: Path, database_url: str, embedding_model: str) -> None:
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    conn_sqlite = sqlite3.connect(sqlite_path)
    conn_sqlite.row_factory = sqlite3.Row

    pool = await asyncpg.create_pool(database_url, init=_init_connection)
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    embed_client = AsyncOpenAI(api_key=openai_key) if openai_key else None

    async with pool.acquire() as pg:
        users = conn_sqlite.execute("SELECT * FROM users").fetchall()
        for row in users:
            await pg.execute(
                """
                INSERT INTO users (tg_user_id, current_mode, is_admin, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tg_user_id) DO NOTHING
                """,
                row["tg_user_id"],
                row["current_mode"],
                bool(row["is_admin"]),
                row["created_at"],
            )

        repos = conn_sqlite.execute("SELECT * FROM user_repos").fetchall()
        for row in repos:
            await pg.execute(
                """
                INSERT INTO user_repos (id, tg_user_id, alias, github_url, default_branch, is_active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (tg_user_id, alias) DO NOTHING
                """,
                row["id"],
                row["tg_user_id"],
                row["alias"],
                row["github_url"],
                row["default_branch"],
                bool(row["is_active"]),
                row["created_at"],
            )
            await pg.execute(
                "SELECT setval(pg_get_serial_sequence('user_repos', 'id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM user_repos))"
            )

        sessions = conn_sqlite.execute("SELECT * FROM agent_sessions").fetchall()
        for row in sessions:
            await pg.execute(
                """
                INSERT INTO agent_sessions (tg_user_id, cursor_agent_id, repo_id, active_run_id, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tg_user_id) DO NOTHING
                """,
                row["tg_user_id"],
                row["cursor_agent_id"],
                row["repo_id"],
                row["active_run_id"],
                row["updated_at"],
            )

        try:
            runs = conn_sqlite.execute("SELECT * FROM run_history ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            runs = []

        for row in runs:
            prompt = row["prompt_summary"]
            result = row["result_summary"] or ""
            title = prompt[:80] + ("…" if len(prompt) > 80 else "")
            embed_text = f"{prompt}\n\n{result}"
            embedding = None
            if embed_client is not None:
                embedding = await _embed(embed_client, embedding_model, embed_text)

            await pg.execute(
                """
                INSERT INTO memory_entries (
                    tg_user_id, repo_id, kind, title, body, source_prompt, embedding,
                    run_id, mode, pr_url, status, duration_ms, created_at
                )
                VALUES ($1, NULL, 'run', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                row["tg_user_id"],
                title,
                result,
                prompt,
                embedding,
                row["run_id"],
                row["mode"],
                row["pr_url"],
                row["status"],
                row["duration_ms"],
                row["created_at"],
            )

    conn_sqlite.close()
    await pool.close()
    print(f"Migrated {len(users)} users, {len(repos)} repos, {len(sessions)} sessions, {len(runs)} runs.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite bot.db to PostgreSQL")
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path("./data/bot.db"),
        help="Path to legacy bot.db",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql://bot:botsecret@localhost:5432/tg_cursor_bot",
        ),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
    )
    args = parser.parse_args()
    asyncio.run(
        migrate(
            sqlite_path=args.sqlite,
            database_url=args.database_url,
            embedding_model=args.embedding_model,
        )
    )


if __name__ == "__main__":
    main()
