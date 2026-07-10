"""Repository config persistence."""

from __future__ import annotations

import asyncpg

from beachops.config.settings import Settings
from beachops.domain.models import RepoConfig
from beachops.services.repo_parse import alias_from_github_url, normalize_github_repo_url


class RepoRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_repos(self, tg_user_id: int) -> list[RepoConfig]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tg_user_id, alias, github_url, default_branch, is_active
                FROM user_repos
                WHERE tg_user_id = $1
                ORDER BY alias
                """,
                tg_user_id,
            )
        return [_row_to_repo(row) for row in rows]

    async def get_active_repo(self, tg_user_id: int) -> RepoConfig | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tg_user_id, alias, github_url, default_branch, is_active
                FROM user_repos
                WHERE tg_user_id = $1 AND is_active = TRUE
                LIMIT 1
                """,
                tg_user_id,
            )
        return _row_to_repo(row) if row else None

    async def get_by_id(self, tg_user_id: int, repo_id: int) -> RepoConfig | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tg_user_id, alias, github_url, default_branch, is_active
                FROM user_repos
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                repo_id,
            )
        return _row_to_repo(row) if row else None

    async def set_active_by_id(self, tg_user_id: int, repo_id: int) -> RepoConfig | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM user_repos
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                repo_id,
            )
            if row is None:
                return None

            await conn.execute(
                "UPDATE user_repos SET is_active = FALSE WHERE tg_user_id = $1",
                tg_user_id,
            )
            await conn.execute(
                "UPDATE user_repos SET is_active = TRUE WHERE id = $1",
                repo_id,
            )
        return await self.get_by_id(tg_user_id, repo_id)

    async def resolve_active_repo(
        self,
        tg_user_id: int,
        settings: Settings,
    ) -> RepoConfig | None:
        """Active repo, or auto-pick the only repo / seed default for empty users."""
        repo = await self.get_active_repo(tg_user_id)
        if repo is not None:
            return repo

        repos = await self.list_repos(tg_user_id)
        if len(repos) == 1:
            return await self.set_active(tg_user_id, repos[0].alias)

        if not repos and settings.has_default_repo():
            return await self.seed_default_repo_for_new_user(tg_user_id, settings)

        return None

    async def set_active(self, tg_user_id: int, alias: str) -> RepoConfig | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM user_repos
                WHERE tg_user_id = $1 AND alias = $2
                """,
                tg_user_id,
                alias,
            )
            if row is None:
                return None

            await conn.execute(
                "UPDATE user_repos SET is_active = FALSE WHERE tg_user_id = $1",
                tg_user_id,
            )
            await conn.execute(
                "UPDATE user_repos SET is_active = TRUE WHERE id = $1",
                row["id"],
            )
        return await self.get_active_repo(tg_user_id)

    async def add_repo(
        self,
        tg_user_id: int,
        alias: str,
        github_url: str,
        default_branch: str = "dev",
        *,
        make_active: bool = False,
    ) -> RepoConfig:
        async with self._pool.acquire() as conn:
            if make_active:
                await conn.execute(
                    "UPDATE user_repos SET is_active = FALSE WHERE tg_user_id = $1",
                    tg_user_id,
                )

            row = await conn.fetchrow(
                """
                INSERT INTO user_repos (tg_user_id, alias, github_url, default_branch, is_active)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tg_user_id, alias) DO UPDATE SET
                    github_url = EXCLUDED.github_url,
                    default_branch = EXCLUDED.default_branch,
                    is_active = EXCLUDED.is_active
                RETURNING id, tg_user_id, alias, github_url, default_branch, is_active
                """,
                tg_user_id,
                alias,
                github_url,
                default_branch,
                make_active,
            )
        assert row is not None
        return _row_to_repo(row)

    async def seed_default_repo_for_new_user(
        self,
        tg_user_id: int,
        settings: Settings,
    ) -> RepoConfig | None:
        if not settings.has_default_repo():
            return None
        github_url = normalize_github_repo_url(settings.default_repo_url)
        return await self.add_repo(
            tg_user_id,
            alias=alias_from_github_url(github_url),
            github_url=github_url,
            default_branch=settings.default_branch,
            make_active=True,
        )


def _row_to_repo(row: asyncpg.Record) -> RepoConfig:
    return RepoConfig(
        id=row["id"],
        tg_user_id=row["tg_user_id"],
        alias=row["alias"],
        github_url=row["github_url"],
        default_branch=row["default_branch"],
        is_active=bool(row["is_active"]),
    )
