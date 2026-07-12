"""Tests for Redis hot-path caches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
    await cache.set_dashboard("owner:1", {"ok": True})
    assert (await cache.get_dashboard("owner:1")) == {"ok": True}
    await cache.bump_dashboard_generation()
    assert await cache.get_dashboard("owner:1") is None


@pytest.mark.asyncio
async def test_dashboard_set_uses_pinned_generation_not_current() -> None:
    """Slow build started at gen N must not poison gen N+1 after a bump."""
    cache = HotCache(FakeRedis())  # type: ignore[arg-type]
    gen0 = await cache.dashboard_generation()
    await cache.bump_dashboard_generation()
    await cache.set_dashboard("owner:1", {"runtime": "cloud"}, generation=gen0)
    assert await cache.get_dashboard("owner:1") is None
    await cache.set_dashboard(
        "owner:1", {"runtime": "windows"}, generation=await cache.dashboard_generation()
    )
    assert (await cache.get_dashboard("owner:1")) == {"runtime": "windows"}


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
