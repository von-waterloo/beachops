"""Streaming speech synthesis for redacted BeachOps responses."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

from openai import AsyncOpenAI

from beachops.domain.voice_persona import SPARTAN_TTS_INSTRUCTIONS, to_spoken_briefing

logger = logging.getLogger(__name__)

# ~200 ms PCM16 mono @ 24 kHz — fewer WebSocket frames on mobile clients.
TTS_OUT_CHUNK_BYTES = 9_600


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
                pending = b""
                async for chunk in response.iter_bytes():
                    pending += chunk
                    while len(pending) >= TTS_OUT_CHUNK_BYTES:
                        take = TTS_OUT_CHUNK_BYTES - (TTS_OUT_CHUNK_BYTES % 2)
                        yield pending[:take]
                        pending = pending[take:]
                even_length = len(pending) - (len(pending) % 2)
                if even_length:
                    yield pending[:even_length]
        except Exception:
            logger.exception("TTS stream failed", extra={"action": "tts"})
            raise
