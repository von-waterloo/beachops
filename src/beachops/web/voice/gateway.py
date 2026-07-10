"""Authenticated server-side bridge for realtime voice transcription."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI


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
        model: str = "gpt-realtime-whisper",
        language: str = "ru",
        limits: VoiceGatewayLimits | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._language = language
        self._limits = limits or VoiceGatewayLimits()

    async def run(
        self,
        websocket: WebSocket,
        *,
        on_plan_request: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        total_bytes = 0
        last_sequence = -1
        async with self._client.realtime.connect(model=self._model) as connection:
            await connection.session.update(
                session={
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "noise_reduction": {"type": "near_field"},
                            "transcription": {
                                "model": self._model,
                                "delay": "minimal",
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
                            await websocket.send_json(
                                {"type": "error", "code": "chunk_too_large"}
                            )
                            continue
                        total_bytes += len(audio)
                        if total_bytes > self._limits.max_session_bytes:
                            await websocket.send_json(
                                {"type": "error", "code": "session_limit"}
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
                    import json

                    try:
                        event = json.loads(message)
                        sequence = int(event.get("seq", last_sequence + 1))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        await websocket.send_json(
                            {"type": "error", "code": "invalid_event"}
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
                                {"type": "error", "code": "invalid_transcript"}
                            )
                            continue
                        job_id = await on_plan_request(transcript)
                        await websocket.send_json(
                            {"type": "plan.started", "jobId": job_id}
                        )
                    elif event_type == "ping":
                        await websocket.send_json(
                            {"type": "pong", "seq": sequence}
                        )
            except WebSocketDisconnect:
                pass
            finally:
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
                await websocket.send_json({"type": "error", "code": str(code)})
