"""Encrypted GitHub OAuth tokens per user."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class UserGithubToken:
    tg_user_id: int
    access_token_enc: str
    github_login: str | None
    scopes: str
    updated_at: datetime
    created_at: datetime


class GithubTokenRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, tg_user_id: int) -> UserGithubToken | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tg_user_id, access_token_enc, github_login, scopes,
                       updated_at, created_at
                FROM user_github_tokens
                WHERE tg_user_id = $1
                """,
                tg_user_id,
            )
        if row is None:
            return None
        return UserGithubToken(
            tg_user_id=int(row["tg_user_id"]),
            access_token_enc=str(row["access_token_enc"]),
            github_login=row["github_login"],
            scopes=str(row["scopes"]),
            updated_at=row["updated_at"],
            created_at=row["created_at"],
        )

    async def upsert(
        self,
        tg_user_id: int,
        *,
        access_token_enc: str,
        github_login: str | None,
        scopes: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_github_tokens (
                    tg_user_id, access_token_enc, github_login, scopes
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tg_user_id) DO UPDATE SET
                    access_token_enc = EXCLUDED.access_token_enc,
                    github_login = EXCLUDED.github_login,
                    scopes = EXCLUDED.scopes,
                    updated_at = now()
                """,
                tg_user_id,
                access_token_enc,
                github_login,
                scopes,
            )

    async def delete(self, tg_user_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_github_tokens WHERE tg_user_id = $1",
                tg_user_id,
            )
