"""OpenAI text embeddings with optional Redis cache."""

from __future__ import annotations

import hashlib
import logging
import struct

from openai import AsyncOpenAI
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_EMBED_PREFIX = "beachops:cache:embed:"
_EMBED_TTL_SEC = 7 * 24 * 3600


class EmbeddingService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        redis: Redis | None = None,
        cache_ttl_sec: int = _EMBED_TTL_SEC,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._redis = redis
        self._cache_ttl_sec = max(60, cache_ttl_sec)

    def _cache_key(self, chunk: str) -> str:
        digest = hashlib.sha256(
            f"{self._model}\n{chunk}".encode("utf-8")
        ).hexdigest()
        return f"{_EMBED_PREFIX}{digest}"

    async def embed(self, text: str, *, max_chars: int = 8000) -> list[float] | None:
        chunk = text.strip()
        if not chunk:
            return None
        if len(chunk) > max_chars:
            chunk = chunk[:max_chars]

        cache_key = self._cache_key(chunk) if self._redis is not None else None
        if cache_key is not None and self._redis is not None:
            cached = await self._redis.get(cache_key)
            if cached is not None:
                try:
                    return _unpack_embedding(cached)
                except (TypeError, struct.error, ValueError):
                    logger.warning("Corrupt embedding cache entry; refetching")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=chunk,
            )
        except Exception:
            logger.exception("Embedding request failed")
            return None

        vector = list(response.data[0].embedding)
        if cache_key is not None and self._redis is not None:
            await self._redis.set(
                cache_key,
                _pack_embedding(vector),
                ex=self._cache_ttl_sec,
            )
        return vector


def _pack_embedding(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_embedding(raw: bytes | str) -> list[float]:
    data = raw.encode("latin-1") if isinstance(raw, str) else raw
    if len(data) % 4 != 0 or not data:
        raise ValueError("invalid embedding blob")
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))
