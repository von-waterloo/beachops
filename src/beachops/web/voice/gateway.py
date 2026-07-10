"""Authenticated server-side bridge for realtime voice transcription."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI

from beachops.services.logging_config import bind_log_context

logger = logging.getLogger(__name__)

# OpenAI rejects input_audio_buffer.commit below ~100ms of PCM16 mono @ 24 kHz.
MIN_COMMIT_AUDIO_BYTES = 24_000 * 2 // 10  # 4800 bytes


def can_commit_audio_buffer(buffered_bytes: int) -> bool:
    """True when the provider buffer has enough PCM to accept a commit."""
    return buffered_bytes >= MIN_COMMIT_AUDIO_BYTES


@dataclass(frozen=True)
class VoiceGatewayLimits:
    max_session_bytes: int = 24_000 * 2 * 60 * 5
    max_chunk_bytes: int = 24_000 * 2


class RealtimeVoiceGateway:
    """Proxy PCM audio to OpenAI without exposing provider keys to clients."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-realtime",
        transcription_model: str = "gpt-4o-transcribe",
        language: str = "ru",
        limits: VoiceGatewayLimits | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._transcription_model = transcription_model
        self._language = language
        self._limits = limits or VoiceGatewayLimits()

    async def run(
        self,
        websocket: WebSocket,
        *,
        on_plan_request: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        session_bytes = 0
        buffered_bytes = 0
        last_sequence = -1
        started = time.monotonic()
        logger.info(
            "Voice gateway connecting to provider",
            extra={"action": "voice_provider_connect"},
        )
        try:
            connection_cm = self._client.realtime.connect(model=self._model)
        except Exception:
            logger.exception(
                "Voice provider connect failed",
                extra={"action": "voice_provider_connect", "error_code": "connect_failed"},
            )
            raise
        async with connection_cm as connection:
            logger.info(
                "Voice provider connected model=%s transcription=%s",
                self._model,
                self._transcription_model,
                extra={"action": "voice_provider_ready"},
            )
            await connection.session.update(
                session={
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "noise_reduction": {"type": "near_field"},
                            "transcription": {
                                "model": self._transcription_model,
                                "language": self._language,
                            },
                            "turn_detection": None,
                        }
                    },
                }
            )
            events_task = asyncio.create_task(
                self._forward_provider_events(connection, websocket)
            )
            try:
                while True:
                    incoming = await websocket.receive()
                    if incoming.get("type") == "websocket.disconnect":
                        break

                    audio = incoming.get("bytes")
                    if audio is not None:
                        if len(audio) > self._limits.max_chunk_bytes:
                            logger.warning(
                                "Voice chunk too large",
                                extra={
                                    "action": "voice_chunk",
                                    "error_code": "chunk_too_large",
                                },
                            )
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "chunk_too_large",
                                    "message": "Audio chunk too large",
                                }
                            )
                            continue
                        session_bytes += len(audio)
                        if session_bytes > self._limits.max_session_bytes:
                            logger.warning(
                                "Voice session byte limit reached",
                                extra={
                                    "action": "voice_session",
                                    "error_code": "session_limit",
                                },
                            )
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "session_limit",
                                    "message": "Voice session limit reached",
                                }
                            )
                            await websocket.close(code=1009)
                            break
                        buffered_bytes += len(audio)
                        await connection.input_audio_buffer.append(
                            audio=base64.b64encode(audio).decode("ascii")
                        )
                        continue

                    message = incoming.get("text")
                    if not message:
                        continue

                    try:
                        event = json.loads(message)
                        sequence = int(event.get("seq", last_sequence + 1))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        await websocket.send_json(
                            {
                                "type": "error",
                                "code": "invalid_event",
                                "message": "Invalid voice event",
                            }
                        )
                        continue
                    if sequence <= last_sequence:
                        continue
                    last_sequence = sequence
                    event_type = event.get("type")
                    if event_type in {"commit", "audio.end"}:
                        # Never call provider commit on empty/short buffer —
                        # OpenAI returns "buffer too small … 0.00ms".
                        if not can_commit_audio_buffer(buffered_bytes):
                            if buffered_bytes > 0:
                                await connection.input_audio_buffer.clear()
                            buffered_bytes = 0
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "empty_audio",
                                    "message": (
                                        "Слишком коротко — подержите кнопку "
                                        "и говорите не меньше секунды."
                                    ),
                                }
                            )
                            continue
                        await connection.input_audio_buffer.commit()
                        buffered_bytes = 0
                    elif event_type in {"clear", "barge_in", "session.cancel"}:
                        await connection.input_audio_buffer.clear()
                        buffered_bytes = 0
                    elif event_type == "audio.start":
                        buffered_bytes = 0
                        await websocket.send_json({"type": "audio.ready"})
                    elif event_type == "plan.request" and on_plan_request is not None:
                        transcript = str(event.get("transcript", "")).strip()
                        if not transcript or len(transcript) > 4000:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "invalid_transcript",
                                    "message": "Transcript is empty or too long",
                                }
                            )
                            continue
                        job_id = await on_plan_request(transcript)
                        bind_log_context(job_id=str(job_id))
                        logger.info(
                            "Voice plan requested",
                            extra={
                                "action": "voice_plan_request",
                                "job_id": str(job_id),
                            },
                        )
                        await websocket.send_json(
                            {"type": "plan.started", "jobId": job_id}
                        )
                    elif event_type == "ping":
                        await websocket.send_json(
                            {"type": "pong", "seq": sequence}
                        )
            except WebSocketDisconnect:
                logger.info(
                    "Voice client disconnected",
                    extra={"action": "voice_disconnect"},
                )
            finally:
                duration_ms = int((time.monotonic() - started) * 1000)
                logger.info(
                    "Voice gateway session ended bytes=%s",
                    session_bytes,
                    extra={
                        "action": "voice_session_end",
                        "duration_ms": duration_ms,
                    },
                )
                events_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await events_task

    async def _forward_provider_events(self, connection, websocket: WebSocket) -> None:
        partials: dict[str, str] = {}
        async for event in connection:
            event_type = getattr(event, "type", "")
            if event_type == "conversation.item.input_audio_transcription.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    item_id = str(getattr(event, "item_id", "current"))
                    partials[item_id] = f"{partials.get(item_id, '')}{delta}"
                    await websocket.send_json(
                        {
                            "type": "transcript.partial",
                            "text": partials[item_id],
                            "eventId": getattr(event, "event_id", None),
                        }
                    )
            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = getattr(event, "transcript", "")
                partials.pop(str(getattr(event, "item_id", "current")), None)
                logger.info(
                    "Voice transcript finalized chars=%s",
                    len(transcript or ""),
                    extra={"action": "voice_transcript_final"},
                )
                await websocket.send_json(
                    {
                        "type": "transcript.final",
                        "text": transcript,
                        "eventId": getattr(event, "event_id", None),
                    }
                )
            elif event_type == "input_audio_buffer.committed":
                await websocket.send_json({"type": "audio.committed"})
            elif event_type == "error":
                error = getattr(event, "error", None)
                code = getattr(error, "code", None) or "provider_error"
                message = getattr(error, "message", None) or "Voice provider error"
                logger.warning(
                    "Voice provider error event",
                    extra={
                        "action": "voice_provider_error",
                        "error_code": str(code),
                    },
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": str(code),
                        "message": str(message),
                    }
                )
