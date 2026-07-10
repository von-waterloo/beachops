"""PostgreSQL connection pool."""

from __future__ import annotations

import logging

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        init=_init_connection,
    )
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    logger.info("Connected to PostgreSQL")
    return pool


async def check_postgres(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ext = await conn.fetchval(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        )
        if ext is None:
            raise RuntimeError(
                "pgvector extension is missing. Run: alembic upgrade head"
            )
