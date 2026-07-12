"""Streaming speech synthesis for redacted BeachOps responses."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

from openai import AsyncOpenAI

from beachops.domain.voice_persona import SPARTAN_TTS_INSTRUCTIONS, to_spoken_briefing

logger = logging.getLogger(__name__)

# ~200 ms PCM16 mono @ 24 kHz — fewer WebSocket frames on mobile clients.
# Kept even so every yielded frame is a whole PCM16 sample frame; the client
# scheduler lays them back-to-back without splitting a sample across chunks.
TTS_OUT_CHUNK_BYTES = 9_600


async def chunk_pcm_stream(
    source: AsyncIterator[bytes],
    *,
    chunk_bytes: int = TTS_OUT_CHUNK_BYTES,
) -> AsyncIterator[bytes]:
    """Re-chunk an arbitrary byte stream into even PCM16 frames of ~chunk_bytes.

    Provider TTS streams arrive in arbitrary byte boundaries that may split a
    16-bit sample. This accumulator yields only whole-sample frames of a fixed
    size (so the client can schedule them contiguously) and flushes any even
    tail at the end — dropping a lone odd byte that would otherwise produce a
    click at the seam.
    """
    pending = b""
    async for chunk in source:
        pending += chunk
        while len(pending) >= chunk_bytes:
            take = chunk_bytes - (chunk_bytes % 2)
            yield pending[:take]
            pending = pending[take:]
    even_length = len(pending) - (len(pending) % 2)
    if even_length:
        yield pending[:even_length]


class SpeechService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice: str,
        instructions: str | None = None,
        redact: Callable[[str], str] | None = None,
        max_chars: int = 900,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._voice = voice
        self._instructions = (instructions or SPARTAN_TTS_INSTRUCTIONS).strip()
        self._redact = redact or (lambda value: value)
        self._max_chars = max_chars

    async def stream_pcm(self, text: str) -> AsyncIterator[bytes]:
        safe_text = to_spoken_briefing(self._redact(text), max_chars=self._max_chars)
        if not safe_text:
            logger.warning(
                "TTS skipped empty briefing",
                extra={"action": "tts", "error_code": "empty_briefing"},
            )
            return
        create_kwargs: dict = {
            "model": self._model,
            "voice": self._voice,
            "input": safe_text,
            "response_format": "pcm",
        }
        # gpt-4o-mini-tts (+ dated snapshots) accept steerable style instructions.
        if self._instructions and "tts" in self._model:
            create_kwargs["instructions"] = self._instructions
        logger.info(
            "TTS stream start chars=%s",
            len(safe_text),
            extra={"action": "tts"},
        )
        try:
            async with self._client.audio.speech.with_streaming_response.create(
                **create_kwargs,
            ) as response:
                async for frame in chunk_pcm_stream(response.iter_bytes()):
                    yield frame
        except Exception:
            logger.exception("TTS stream failed", extra={"action": "tts"})
            raise
