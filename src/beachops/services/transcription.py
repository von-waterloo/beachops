"""OpenAI speech-to-text for Telegram voice messages."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe_bytes(self, audio: bytes, filename: str = "voice.ogg") -> str:
        buffer = BytesIO(audio)
        buffer.name = filename
        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=buffer,
        )
        text = (response.text or "").strip()
        if text:
            logger.info(
                "Transcribed %d bytes -> %d chars",
                len(audio),
                len(text),
                extra={"action": "transcribe"},
            )
        else:
            logger.warning(
                "Empty transcription for %d bytes",
                len(audio),
                extra={"action": "transcribe", "error_code": "empty_transcript"},
            )
        return text

    async def transcribe_file(self, path: Path) -> str:
        data = path.read_bytes()
        return await self.transcribe_bytes(data, filename=path.name)
