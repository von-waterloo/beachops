"""Tests for Redis hot-path caches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from beachops.db.repositories.system_state import SystemStateRepository
from beachops.domain.security import Role
from beachops.services.embedding_service import (
    EmbeddingService,
    _pack_embedding,
    _unpack_embedding,
)
from beachops.services.hot_cache import HotCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes | str, ex: int | None = None) -> bool:
        raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
        self.values[key] = raw
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, b"0"))
        current += 1
        self.values[key] = str(current).encode("utf-8")
        return current


@pytest.mark.asyncio
async def test_hot_cache_user_ready_roundtrip() -> None:
    cache = HotCache(FakeRedis())  # type: ignore[arg-type]
    assert await cache.get_user_ready_role(7) is None
    await cache.set_user_ready(7, "owner")
    assert await cache.get_user_ready_role(7) == "owner"


@pytest.mark.asyncio
async def test_dashboard_cache_invalidates_on_generation_bump() -> None:
    cache = HotCache(FakeRedis())  # type: ignore[arg-type]
    await cache.set_dashboard("owner:1", {"panic": False})
    assert (await cache.get_dashboard("owner:1")) == {"panic": False}
    await cache.bump_dashboard_generation()
    assert await cache.get_dashboard("owner:1") is None


@pytest.mark.asyncio
async def test_panic_warm_does_not_bump_dashboard() -> None:
    cache = HotCache(FakeRedis())  # type: ignore[arg-type]
    await cache.set_dashboard("owner:1", {"ok": True})
    await cache.warm_panic(False)
    assert await cache.dashboard_generation() == 0
    assert (await cache.get_dashboard("owner:1")) == {"ok": True}


@pytest.mark.asyncio
async def test_panic_write_through_skips_postgres_on_hit() -> None:
    redis = FakeRedis()
    cache = HotCache(redis)  # type: ignore[arg-type]
    await cache.warm_panic(True)

    pool = SimpleNamespace(acquire=AsyncMock())
    repo = SystemStateRepository(pool, cache=cache)  # type: ignore[arg-type]
    assert await repo.is_panic_enabled() is True
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_panic_set_updates_cache() -> None:
    redis = FakeRedis()
    cache = HotCache(redis)  # type: ignore[arg-type]
    pool = SimpleNamespace()

    class _Conn:
        async def fetchrow(self, *_args, **_kwargs):
            return {"key": "panic"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    pool.acquire = lambda: _Conn()
    repo = SystemStateRepository(pool, cache=cache)  # type: ignore[arg-type]
    await repo.set_panic(True, actor_id=1, actor_role=Role.OWNER)
    assert await cache.get_panic() is True
    assert await cache.dashboard_generation() == 1


def test_embedding_pack_roundtrip() -> None:
    vector = [0.1, -0.25, 1.5]
    assert _unpack_embedding(_pack_embedding(vector)) == pytest.approx(vector)


@pytest.mark.asyncio
async def test_embedding_service_uses_redis_cache() -> None:
    redis = FakeRedis()
    service = EmbeddingService(api_key="test", model="text-embedding-3-small", redis=redis)  # type: ignore[arg-type]
    vector = [0.5, 0.25, -0.125]
    key = service._cache_key("hello")
    await redis.set(key, _pack_embedding(vector), ex=60)

    service._client = SimpleNamespace(  # type: ignore[assignment]
        embeddings=SimpleNamespace(create=AsyncMock(side_effect=AssertionError("should not call")))
    )
    assert await service.embed("hello") == pytest.approx(vector)
