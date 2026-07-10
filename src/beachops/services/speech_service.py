"""Streaming speech synthesis for redacted BeachOps responses."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
import re

from openai import AsyncOpenAI


class SpeechService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice: str,
        redact: Callable[[str], str] | None = None,
        max_chars: int = 4000,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._voice = voice
        self._redact = redact or (lambda value: value)
        self._max_chars = max_chars

    async def stream_pcm(self, text: str) -> AsyncIterator[bytes]:
        safe_text = _speech_safe(self._redact(text)).strip()
        if not safe_text:
            return
        safe_text = safe_text[: self._max_chars]
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=self._voice,
            input=safe_text,
            response_format="pcm",
        ) as response:
            pending = b""
            async for chunk in response.iter_bytes():
                data = pending + chunk
                even_length = len(data) - (len(data) % 2)
                if even_length:
                    yield data[:even_length]
                pending = data[even_length:]


_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_URL_RE = re.compile(r"https?://\S+")


def _speech_safe(text: str) -> str:
    value = _CODE_BLOCK_RE.sub(" Фрагмент кода доступен на экране. ", text)
    value = _URL_RE.sub(" ссылка доступна на экране ", value)
    return re.sub(r"\s+", " ", value)
