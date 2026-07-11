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
from beachops.domain.voice_persona import BEACHOPS_STT_PROMPT

logger = logging.getLogger(__name__)


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
        input_transcribe_model: str = "gpt-4o-transcribe",
        language: str = "ru",
        transcription_prompt: str | None = None,
        limits: VoiceGatewayLimits | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._input_transcribe_model = input_transcribe_model
        self._language = language
        prompt = (transcription_prompt if transcription_prompt is not None else BEACHOPS_STT_PROMPT).strip()
        self._transcription_prompt = prompt
        self._limits = limits or VoiceGatewayLimits()

    def _session_update_payload(self) -> dict:
        # gpt-realtime requires session.type=realtime. type=transcription is only
        # for gpt-realtime-whisper connect models (not available on this key).
        transcription: dict = {
            "model": self._input_transcribe_model,
            "language": self._language,
        }
        # prompt steers vocabulary for gpt-4o(-mini)-transcribe; not for whisper-1 /
        # gpt-realtime-whisper GA sessions.
        if self._transcription_prompt and "whisper" not in self._input_transcribe_model:
            transcription["prompt"] = self._transcription_prompt
        if (
            "whisper" in self._input_transcribe_model
            and self._input_transcribe_model != "whisper-1"
        ):
            transcription["delay"] = "minimal"
        return {
            "type": "realtime",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "noise_reduction": {"type": "near_field"},
                    "transcription": transcription,
                    "turn_detection": None,
                }
            },
        }

    async def run(
        self,
        websocket: WebSocket,
        *,
        on_plan_request: Callable[..., Awaitable[str]] | None = None,
    ) -> None:
        total_bytes = 0
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
                "Voice provider connected",
                extra={"action": "voice_provider_ready"},
            )
            await connection.session.update(session=self._session_update_payload())
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
                                    "message": "Слишком большой аудио-чанк",
                                }
                            )
                            continue
                        total_bytes += len(audio)
                        if total_bytes > self._limits.max_session_bytes:
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
                                    "message": "Лимит голосовой сессии исчерпан",
                                }
                            )
                            await websocket.close(code=1009)
                            break
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
                                "message": "Некорректное голосовое событие",
                            }
                        )
                        continue
                    if sequence <= last_sequence:
                        continue
                    last_sequence = sequence
                    event_type = event.get("type")
                    if event_type in {"commit", "audio.end"}:
                        await connection.input_audio_buffer.commit()
                    elif event_type in {"clear", "barge_in", "session.cancel"}:
                        await connection.input_audio_buffer.clear()
                    elif event_type == "audio.start":
                        await websocket.send_json({"type": "audio.ready"})
                    elif event_type == "plan.request" and on_plan_request is not None:
                        transcript = str(event.get("transcript", "")).strip()
                        if not transcript or len(transcript) > 4000:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "invalid_transcript",
                                    "message": "Пустой или слишком длинный транскрипт",
                                }
                            )
                            continue
                        mode_raw = str(event.get("mode") or "plan").strip().lower()
                        from beachops.domain.models import UserMode

                        try:
                            mode = UserMode(mode_raw)
                        except ValueError:
                            mode = UserMode.PLAN
                        try:
                            job_id = await on_plan_request(transcript, mode)
                        except TypeError:
                            # Back-compat for single-arg callbacks in tests.
                            try:
                                job_id = await on_plan_request(transcript)
                            except Exception as exc:
                                logger.warning(
                                    "Voice plan request failed",
                                    extra={
                                        "action": "voice_plan_request",
                                        "error_code": "dispatch_blocked",
                                    },
                                )
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "code": "dispatch_blocked",
                                        "message": str(exc) or "Запрос заблокирован",
                                    }
                                )
                                continue
                        except Exception as exc:
                            logger.warning(
                                "Voice plan request failed",
                                extra={
                                    "action": "voice_plan_request",
                                    "error_code": "dispatch_blocked",
                                },
                            )
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "dispatch_blocked",
                                    "message": str(exc) or "Запрос заблокирован",
                                }
                            )
                            continue
                        bind_log_context(job_id=str(job_id))
                        logger.info(
                            "Voice plan requested",
                            extra={
                                "action": "voice_plan_request",
                                "job_id": str(job_id),
                            },
                        )
                        await websocket.send_json(
                            {
                                "type": "plan.started",
                                "jobId": job_id,
                                "mode": mode.value,
                            }
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
                    total_bytes,
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
