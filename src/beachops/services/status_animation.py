"""Animated waiting indicators for Telegram status messages."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from telegram import Message
from telegram.constants import ChatAction
from telegram.error import BadRequest, RetryAfter

logger = logging.getLogger(__name__)

StatusPresetKind = Literal[
    "recognition",
    "downloading",
    "downloading_document",
    "extracting_document",
    "downloading_images",
    "starting",
    "run_started",
    "waiting_signal",
    "waiting",
]

_SPINNER = ("◐", "◓", "◑", "◒")
_PROGRESS = ("▱▱▱▱", "▰▱▱▱", "▰▰▱▱", "▰▰▰▱", "▰▰▰▰")
_ELAPSED_AFTER_SEC = 1.0


@dataclass(frozen=True, slots=True)
class StatusPreset:
    icon: str
    label: str
    frames: tuple[str, ...]
    chat_action: ChatAction
    hint: str | None = None


_PRESETS: dict[StatusPresetKind, StatusPreset] = {
    "downloading": StatusPreset(
        "📥",
        "Скачиваю аудио",
        _PROGRESS,
        ChatAction.UPLOAD_VOICE,
    ),
    "downloading_document": StatusPreset(
        "📥",
        "Скачиваю документ",
        _PROGRESS,
        ChatAction.UPLOAD_DOCUMENT,
    ),
    "extracting_document": StatusPreset(
        "📄",
        "Извлекаю текст",
        _SPINNER,
        ChatAction.TYPING,
        hint="Обычно 2–15 сек",
    ),
    "downloading_images": StatusPreset(
        "📷",
        "Скачиваю изображения",
        _PROGRESS,
        ChatAction.UPLOAD_PHOTO,
    ),
    "recognition": StatusPreset(
        "🎤",
        "Распознаю речь",
        _SPINNER,
        ChatAction.TYPING,
        hint="Обычно 3–10 сек",
    ),
    "starting": StatusPreset(
        "⚡",
        "Подключаю агента",
        _PROGRESS,
        ChatAction.TYPING,
    ),
    "run_started": StatusPreset(
        "🚀",
        "Агент готов",
        _PROGRESS,
        ChatAction.TYPING,
        hint="Запускаю задачу…",
    ),
    "waiting_signal": StatusPreset(
        "💭",
        "Жду первый сигнал",
        _SPINNER,
        ChatAction.TYPING,
        hint="Инструменты и ответ появятся ниже",
    ),
    "waiting": StatusPreset(
        "💭",
        "Агент думает",
        _SPINNER,
        ChatAction.TYPING,
        hint="Ответ появится здесь же",
    ),
}


class AnimatedStatus:
    """Cycles frames in a status message until stopped."""

    def __init__(
        self,
        message: Message,
        *,
        preset: StatusPresetKind,
        header_lines: list[str] | None = None,
        interval: float = 1.0,
    ) -> None:
        self._message = message
        self._preset_kind = preset
        self._preset = _PRESETS[preset]
        self._header_lines = list(header_lines or [])
        self._interval = interval
        self._frame_idx = 0
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._last_text = ""
        self._started_at = 0.0
        self._extra_lines: list[str] = []

    async def __aenter__(self) -> AnimatedStatus:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._started_at = time.monotonic()
        await self._tick(force=True)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def set_extra_lines(self, lines: list[str]) -> None:
        self._extra_lines = [line for line in lines if line.strip()]

    async def set_preset(self, preset: StatusPresetKind) -> None:
        if self._stopped:
            return
        if preset == self._preset_kind:
            return
        self._preset_kind = preset
        self._preset = _PRESETS[preset]
        self._frame_idx = 0
        await self._tick(force=True)

    async def _loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._interval)
                if self._stopped:
                    break
                await self._tick()
        except asyncio.CancelledError:
            raise

    async def _tick(self, *, force: bool = False) -> None:
        frame = self._preset.frames[self._frame_idx % len(self._preset.frames)]
        self._frame_idx += 1
        text = self._compose(frame)
        if not force and text == self._last_text:
            return
        self._last_text = text

        bot = self._message.get_bot()
        chat_id = self._message.chat_id
        try:
            await bot.send_chat_action(chat_id=chat_id, action=self._preset.chat_action)
        except Exception:
            logger.debug("chat_action failed", exc_info=True)

        try:
            await self._message.edit_text(text)
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.warning("status animation edit failed: %s", exc)
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after))
            if not self._stopped:
                await self._tick(force=True)

    def _compose(self, frame: str) -> str:
        return _compose_status(
            self._preset_kind,
            frame,
            self._header_lines,
            extra_lines=self._extra_lines,
            elapsed=self._elapsed_suffix(),
        )

    def _elapsed_suffix(self) -> str:
        if self._started_at <= 0:
            return ""
        elapsed_sec = time.monotonic() - self._started_at
        if elapsed_sec < _ELAPSED_AFTER_SEC:
            return ""
        return f"⏱ {int(elapsed_sec)} сек"


def initial_status_text(*, preset: StatusPresetKind, header_lines: list[str] | None = None) -> str:
    return _compose_status(preset, _PRESETS[preset].frames[0], header_lines)


def run_activity_frame(index: int) -> str:
    return _SPINNER[index % len(_SPINNER)]


def format_run_activity_line(frame: str, *, elapsed_sec: int = 0) -> str:
    """Compact activity line while a run streams content (below header, above body)."""
    line = f"💭 Агент работает  {frame}"
    if elapsed_sec >= 1:
        line = f"{line}\n⏱ {elapsed_sec} сек"
    return line


def _compose_status(
    preset: StatusPresetKind,
    frame: str,
    header_lines: list[str] | None,
    *,
    hint: bool = True,
    extra_lines: list[str] | None = None,
    elapsed: str = "",
) -> str:
    p = _PRESETS[preset]
    status_line = f"{p.icon} {p.label}  {frame}"
    lines = [*header_lines, "", status_line] if header_lines else [status_line]
    if hint and p.hint:
        # Sent as plain text (no parse_mode) — underscores would show up literally.
        lines.append(p.hint)
    if extra_lines:
        lines.extend(extra_lines)
    if elapsed:
        lines.append(elapsed)
    return "\n".join(lines)
