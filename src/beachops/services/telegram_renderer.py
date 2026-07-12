"""Telegram message streaming via edit_message_text."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from contextlib import suppress
from typing import TYPE_CHECKING

from telegram import LinkPreviewOptions, Message, MessageEntity
from telegram.constants import ChatAction
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from beachops.domain.models import UserMode
from beachops.services.inline_keyboards import post_run_keyboard, run_activity_keyboard
from beachops.services.markdown_format import (
    format_markdown_message,
    format_readable_message,
)
from beachops.services.status_animation import (
    AnimatedStatus,
    format_run_activity_line,
    initial_status_text,
    run_activity_frame,
)
from beachops.services.stream_bridge import StreamState
from beachops.services.stream_display import ThinkingDisplay
from beachops.services.ui_copy import agent_cursor_link

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
        current_token_key: str | None = None,
        available_token_keys: Sequence[str] | None = None,
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
        self._current_token_key = current_token_key
        self._available_token_keys = available_token_keys
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
        self._flush_lock = asyncio.Lock()
        self._activity_task = asyncio.create_task(self._activity_loop())

    async def update(self, state: StreamState) -> None:
        """Best-effort UI update. Never raise into the Cursor run loop."""
        if self._closed:
            return
        try:
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
        except Exception:
            logger.warning("Telegram stream update failed; continuing run", exc_info=True)

    async def shutdown(self) -> None:
        """Stop background activity without changing the message (cancel / abort)."""
        self._closed = True
        await self._stop_activity_loop()
        await self._cancel_edit_task()

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
        await self._cancel_edit_task()
        await self._flush(footer=footer, force=True, reply_markup=reply_markup)

    async def _delayed_flush(self, delay: float) -> None:
        await asyncio.sleep(max(0.0, delay))
        if not self._closed and self._pending is not None:
            await self._flush()

    async def _cancel_edit_task(self) -> None:
        task = self._edit_task
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    async def _stop_activity_loop(self) -> None:
        task = self._activity_task
        if task is None:
            return
        self._activity_task = None
        task.cancel()
        # In-flight pulse flush may raise (network); never abort finalize.
        with suppress(asyncio.CancelledError, Exception):
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
                    try:
                        await self._flush(from_pulse=True)
                    except Exception:
                        logger.debug("run activity flush failed", exc_info=True)
        except asyncio.CancelledError:
            raise

    async def _ensure_reply_markup(self, markup) -> None:
        """Apply keyboard when edit_text was a no-op (text unchanged)."""
        if markup is None:
            return
        try:
            await self._message.edit_reply_markup(reply_markup=markup)
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.debug("edit_reply_markup failed: %s", exc)
        except Exception:
            logger.debug("edit_reply_markup failed", exc_info=True)

    async def _flush(
        self,
        *,
        footer: str = "",
        force: bool = False,
        from_pulse: bool = False,
        reply_markup=None,
    ) -> None:
        retry_after: float | None = None
        async with self._flush_lock:
            retry_after = await self._flush_locked(
                footer=footer,
                force=force,
                reply_markup=reply_markup,
            )
        if retry_after is not None and force:
            logger.info("Telegram rate limit, sleeping %ss", retry_after)
            await asyncio.sleep(retry_after)
            await self._flush(footer=footer, force=True, reply_markup=reply_markup)

    async def _flush_locked(
        self,
        *,
        footer: str = "",
        force: bool = False,
        reply_markup=None,
    ) -> float | None:
        """Apply one edit. Returns RetryAfter seconds if rate-limited."""
        if self._pending is None:
            return None
        # After finalize/shutdown never re-apply the cancel keyboard.
        if self._closed and not force:
            return None
        plain_text = self._compose_plain(self._pending, footer)
        if not force and self._answer_text(self._pending):
            plain_text = self._compose_readable_stream(self._pending, footer)
        formatted = self._compose_formatted(self._pending, footer) if force else None
        if reply_markup is None:
            if force:
                markup = post_run_keyboard(
                    is_admin=self._is_admin,
                    current=self._mode,
                    current_model_key=self._current_model_key,
                    current_token_key=self._current_token_key,
                    available_token_keys=self._available_token_keys,
                    with_retry=False,
                )
            else:
                markup = run_activity_keyboard(
                    is_admin=self._is_admin,
                    current=self._mode,
                    current_model_key=self._current_model_key,
                    current_token_key=self._current_token_key,
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
                if force:
                    await self._ensure_reply_markup(markup)
                return None
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
                        if force:
                            await self._ensure_reply_markup(markup)
                        return None
                    raise
            else:
                logger.warning("edit_text failed: %s", exc)
                return None
        except RetryAfter as exc:
            return float(exc.retry_after)
        except (TimedOut, NetworkError) as exc:
            # Telegram flakiness must never abort an in-flight Cursor run.
            logger.warning("Telegram edit timed out/network error: %s", exc)
            if force:
                # One more attempt for terminal updates; still swallow failures.
                try:
                    await self._message.edit_text(
                        plain_text,
                        link_preview_options=_NO_PREVIEW,
                        reply_markup=markup,
                    )
                except Exception:
                    logger.warning(
                        "Telegram finalize retry failed; message may stay stale",
                        exc_info=True,
                    )
            return None
        except Exception:
            logger.warning("Telegram edit_text failed unexpectedly", exc_info=True)
            return None

        self._last_edit_at = time.monotonic()
        return None

    def _compose_readable_stream(self, state: StreamState, footer: str) -> str:
        answer = self._answer_text(state)
        readable_body = format_readable_message("", answer, "").strip() if answer else ""
        lines = [self._header]
        agent_extra = self._agent_extra(state)
        if agent_extra:
            lines.append(agent_extra)
        activity = self._activity_line(state)
        if activity:
            lines.extend(["", activity])
        if readable_body:
            lines.extend(["", readable_body])
        elif not answer:
            lines.extend(["", state.render_body(
                thinking_display=self._thinking_display,
                preview_max=self._thinking_preview_chars,
            )])
        if footer:
            lines.extend(["", footer])
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4090] + "…"
        return text

    def _answer_text(self, state: StreamState) -> str:
        text = (state.final_text or state.assistant_text or "").strip()
        if text:
            return text
        # Never promote the empty-stream placeholder into a "final answer".
        body = state.render_body(
            thinking_display=self._thinking_display,
            preview_max=self._thinking_preview_chars,
        ).strip()
        from beachops.services.ui_copy import EMPTY_STREAM_HINT

        if body == EMPTY_STREAM_HINT:
            return ""
        return body

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
        # On finalize with empty body, avoid leaving "Ожидаю ответ агента…".
        from beachops.services.ui_copy import EMPTY_STREAM_HINT

        if self._closed and body.strip() == EMPTY_STREAM_HINT:
            if state.status.lower() in {"finished", "completed"}:
                body = "Готово."
            elif state.status.lower() in {"error", "failed"}:
                body = "Сбой run — смотри лог агента."
            else:
                body = "Агент ещё работает — обновлю, когда будет ответ."
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
    current_token_key: str | None = None,
    reply_to_message_id: int | None = None,
) -> tuple[Message, AnimatedStatus]:
    header_lines = [header]
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=initial_status_text(preset="starting", header_lines=header_lines),
        reply_markup=run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=current_model_key,
            current_token_key=current_token_key,
        ),
        reply_to_message_id=reply_to_message_id,
    )
    animation = AnimatedStatus(message, preset="starting", header_lines=header_lines)
    await animation.start()
    return message, animation
