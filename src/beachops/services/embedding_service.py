"""OpenAI text embeddings."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def embed(self, text: str, *, max_chars: int = 8000) -> list[float] | None:
        chunk = text.strip()
        if not chunk:
            return None
        if len(chunk) > max_chars:
            chunk = chunk[:max_chars]

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=chunk,
            )
        except Exception:
            logger.exception("Embedding request failed")
            return None

        return list(response.data[0].embedding)
