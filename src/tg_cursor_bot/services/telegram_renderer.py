"""Telegram message streaming via edit_message_text."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

from telegram import LinkPreviewOptions, Message, MessageEntity
from telegram.constants import ChatAction
from telegram.error import BadRequest, RetryAfter

from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.services.inline_keyboards import post_run_keyboard, run_activity_keyboard
from tg_cursor_bot.services.markdown_format import (
    format_markdown_message,
    format_readable_message,
)
from tg_cursor_bot.services.status_animation import (
    AnimatedStatus,
    format_run_activity_line,
    initial_status_text,
    run_activity_frame,
)
from tg_cursor_bot.services.stream_bridge import StreamState
from tg_cursor_bot.services.stream_display import ThinkingDisplay
from tg_cursor_bot.services.ui_copy import EMPTY_STREAM_HINT, agent_cursor_link

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _state_has_content(state: StreamState, *, thinking_display: ThinkingDisplay) -> bool:
    return state.has_visible_output(thinking_display=thinking_display)


class TelegramStreamRenderer:
    def __init__(
        self,
        message: Message,
        *,
        header: str,
        is_admin: bool,
        mode: UserMode,
        current_model_key: str,
        min_edit_interval: float = 1.0,
        placeholder_animation: AnimatedStatus | None = None,
        thinking_display: ThinkingDisplay = "none",
        thinking_preview_chars: int = 300,
    ) -> None:
        self._message = message
        self._header = header
        self._is_admin = is_admin
        self._mode = mode
        self._current_model_key = current_model_key
        self._thinking_display = thinking_display
        self._thinking_preview_chars = thinking_preview_chars
        self._min_edit_interval = min_edit_interval
        self._last_edit_at = 0.0
        self._pending: StreamState | None = None
        self._edit_task: asyncio.Task[None] | None = None
        self._closed = False
        self._placeholder_animation = placeholder_animation
        self._activity_frame = 0
        self._run_started_at = time.monotonic()
        self._activity_task = asyncio.create_task(self._activity_loop())

    async def update(self, state: StreamState) -> None:
        if self._closed:
            return
        if self._placeholder_animation and _state_has_content(
            state, thinking_display=self._thinking_display
        ):
            await self._placeholder_animation.stop()
            self._placeholder_animation = None
        self._pending = state
        now = time.monotonic()
        if now - self._last_edit_at >= self._min_edit_interval:
            await self._flush()
        elif self._edit_task is None or self._edit_task.done():
            delay = self._min_edit_interval - (now - self._last_edit_at)
            self._edit_task = asyncio.create_task(self._delayed_flush(delay))

    async def shutdown(self) -> None:
        """Stop background activity without changing the message (cancel / abort)."""
        self._closed = True
        await self._stop_activity_loop()
        if self._edit_task and not self._edit_task.done():
            self._edit_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._edit_task

    async def finalize(
        self,
        state: StreamState,
        footer: str = "",
        *,
        reply_markup=None,
    ) -> None:
        self._closed = True
        await self._stop_activity_loop()
        if self._placeholder_animation:
            await self._placeholder_animation.stop()
            self._placeholder_animation = None
        self._pending = state
        if self._edit_task and not self._edit_task.done():
            self._edit_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._edit_task
        await self._flush(footer=footer, force=True, reply_markup=reply_markup)

    async def _delayed_flush(self, delay: float) -> None:
        await asyncio.sleep(max(0.0, delay))
        if not self._closed and self._pending is not None:
            await self._flush()

    async def _stop_activity_loop(self) -> None:
        task = self._activity_task
        if task is None:
            return
        self._activity_task = None
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _activity_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._min_edit_interval)
                if self._closed:
                    break
                bot = self._message.get_bot()
                try:
                    await bot.send_chat_action(
                        chat_id=self._message.chat_id,
                        action=ChatAction.TYPING,
                    )
                except Exception:
                    logger.debug("run activity chat_action failed", exc_info=True)
                if self._placeholder_animation is not None:
                    continue
                self._activity_frame += 1
                if self._pending is not None:
                    await self._flush(from_pulse=True)
        except asyncio.CancelledError:
            raise

    async def _flush(
        self,
        *,
        footer: str = "",
        force: bool = False,
        from_pulse: bool = False,
        reply_markup=None,
    ) -> None:
        if self._pending is None:
            return
        if from_pulse and not force and self._closed:
            return
        plain_text = self._compose_plain(self._pending, footer)
        formatted = self._compose_formatted(self._pending, footer) if force else None
        if reply_markup is None:
            if force:
                markup = post_run_keyboard(
                    is_admin=self._is_admin,
                    current=self._mode,
                    current_model_key=self._current_model_key,
                    with_retry=False,
                )
            else:
                markup = run_activity_keyboard(
                    is_admin=self._is_admin,
                    current=self._mode,
                    current_model_key=self._current_model_key,
                )
        else:
            markup = reply_markup

        try:
            if formatted is not None:
                text, entities = formatted
                if entities:
                    await self._message.edit_text(
                        text,
                        entities=entities,
                        link_preview_options=_NO_PREVIEW,
                        reply_markup=markup,
                    )
                else:
                    await self._message.edit_text(
                        text,
                        link_preview_options=_NO_PREVIEW,
                        reply_markup=markup,
                    )
            else:
                await self._message.edit_text(
                    plain_text,
                    link_preview_options=_NO_PREVIEW,
                    reply_markup=markup,
                )
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            if formatted is not None:
                logger.warning(
                    "formatted edit_text failed, retrying readable plain: %s", exc
                )
                fallback_text = self._compose_readable_fallback(
                    self._pending, footer
                )
                try:
                    await self._message.edit_text(
                        fallback_text,
                        link_preview_options=_NO_PREVIEW,
                        reply_markup=markup,
                    )
                except BadRequest as retry_exc:
                    if "message is not modified" in str(retry_exc).lower():
                        return
                    raise
            else:
                logger.warning("edit_text failed: %s", exc)
        except RetryAfter as exc:
            logger.info("Telegram rate limit, sleeping %ss", exc.retry_after)
            await asyncio.sleep(float(exc.retry_after))
            if force:
                await self._flush(footer=footer, force=True, reply_markup=reply_markup)
            return

        self._last_edit_at = time.monotonic()

    def _answer_text(self, state: StreamState) -> str:
        return (state.final_text or state.assistant_text or state.render_body()).strip()

    def _agent_extra(self, state: StreamState) -> str:
        if state.agent_id:
            return agent_cursor_link(state.agent_id)
        return ""

    def _show_run_activity(self, state: StreamState) -> bool:
        if self._closed or self._placeholder_animation is not None:
            return False
        return state.status.lower() in {"", "running", "in_progress"}

    def _activity_line(self, state: StreamState) -> str:
        if not self._show_run_activity(state):
            return ""
        elapsed = int(time.monotonic() - self._run_started_at)
        frame = run_activity_frame(self._activity_frame)
        return format_run_activity_line(frame, elapsed_sec=elapsed)

    def _compose_plain(self, state: StreamState, footer: str) -> str:
        body = self._answer_text(state) or state.render_body(
            thinking_display=self._thinking_display,
            preview_max=self._thinking_preview_chars,
        )
        if body == EMPTY_STREAM_HINT and not state.has_visible_output(
            thinking_display=self._thinking_display
        ):
            body = f"_{body}_"
        lines = [self._header]
        agent_extra = self._agent_extra(state)
        if agent_extra:
            lines.append(agent_extra)
        activity = self._activity_line(state)
        if activity:
            lines.extend(["", activity])
        lines.extend(["", body])
        if footer:
            lines.extend(["", footer])
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4090] + "…"
        return text

    def _compose_readable_fallback(self, state: StreamState, footer: str) -> str:
        body = self._answer_text(state)
        if not body:
            return self._compose_plain(state, footer)
        return format_readable_message(self._header, body, footer)

    def _compose_formatted(
        self, state: StreamState, footer: str
    ) -> tuple[str, list[MessageEntity] | None] | None:
        body = self._answer_text(state)
        if not body:
            return None
        return format_markdown_message(self._header, body, footer)


async def send_placeholder(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    header: str,
    *,
    is_admin: bool,
    mode: UserMode,
    current_model_key: str,
) -> tuple[Message, AnimatedStatus]:
    header_lines = [header]
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=initial_status_text(preset="starting", header_lines=header_lines),
        reply_markup=run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=current_model_key,
        ),
    )
    animation = AnimatedStatus(message, preset="starting", header_lines=header_lines)
    await animation.start()
    return message, animation
