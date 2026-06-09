"""Run orchestration for text and voice prompts."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from cursor_sdk import SDKImage
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.config.settings import Settings
from tg_cursor_bot.domain.active_run import ActiveRunInfo
from tg_cursor_bot.domain.cursor_models import resolve_cursor_model
from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.services.agent_slots import RunContext
from tg_cursor_bot.services.job_queue import RunCancelled, SubmitInfo, SubmitResult
from tg_cursor_bot.services.stream_display import resolve_thinking_display
from tg_cursor_bot.services.telegram_renderer import TelegramStreamRenderer, send_placeholder
from tg_cursor_bot.services.ui_copy import (
    access_denied_mode,
    agent_cursor_link,
    build_run_footer,
    build_run_header,
    queue_full_message,
    queued_message,
)

logger = logging.getLogger(__name__)

_LAST_PROMPT_TTL_SEC = 600


async def validate_prompt_request(
    app: AppContext,
    user_id: int,
    *,
    mode: UserMode | None = None,
) -> str | None:
    """Return user-facing error text, or None if the request may proceed."""
    settings = app.settings
    if not settings.is_whitelisted(user_id):
        return None

    if mode is None:
        mode = await app.users.get_mode(user_id)

    if not settings.can_use_mode(user_id, mode):
        return access_denied_mode(mode)

    ctx = await app.agent_slots.get_run_context(user_id)
    if ctx is None:
        from tg_cursor_bot.services.ui_copy import no_repo_selected

        return no_repo_selected()

    return None


def remember_prompt(app: AppContext, user_id: int, prompt: str) -> None:
    app.last_prompts[user_id] = (prompt, time.monotonic())


def get_last_prompt(app: AppContext, user_id: int) -> str | None:
    entry = app.last_prompts.get(user_id)
    if entry is None:
        return None
    prompt, saved_at = entry
    if time.monotonic() - saved_at > _LAST_PROMPT_TTL_SEC:
        app.last_prompts.pop(user_id, None)
        return None
    return prompt


def resolve_history_retry_mode(
    *,
    settings: Settings,
    user_id: int,
    mode_value: str | None,
) -> UserMode | None:
    """Mode stored on a memory run entry, if the user may still use it."""
    try:
        mode = UserMode(mode_value or UserMode.ASK.value)
    except ValueError:
        mode = UserMode.ASK
    if not settings.can_use_mode(user_id, mode):
        return None
    return mode


async def submit_user_prompt(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    prompt: str,
    mode: UserMode | None = None,
    images: Sequence[SDKImage] | None = None,
    notify_queue_full: bool = True,
) -> SubmitInfo:
    app: AppContext = context.application.bot_data["app"]

    if not app.settings.is_whitelisted(user_id):
        return SubmitInfo(SubmitResult.REJECTED)

    if mode is None:
        mode = await app.users.get_mode(user_id)

    error = await validate_prompt_request(app, user_id, mode=mode)
    if error:
        await context.bot.send_message(chat_id=user_id, text=error)
        return SubmitInfo(SubmitResult.REJECTED)

    run_ctx = await app.agent_slots.get_run_context(user_id)
    assert run_ctx is not None

    remember_prompt(app, user_id, prompt)
    await app.agent_slots.maybe_autoname_active(user_id, prompt)

    image_tuple = tuple(images) if images else None

    async def job() -> None:
        await _run_job(context, user_id, prompt, mode, run_ctx, images=image_tuple)

    info = await app.job_queue.submit(user_id, job)
    if info.result == SubmitResult.QUEUED:
        await context.bot.send_message(
            chat_id=user_id,
            text=queued_message(info.queue_position),
        )
    elif info.result == SubmitResult.REJECTED and notify_queue_full:
        await context.bot.send_message(chat_id=user_id, text=queue_full_message())

    return info


async def execute_user_prompt(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    prompt: str,
    mode: UserMode | None = None,
) -> None:
    await submit_user_prompt(context=context, user_id=user_id, prompt=prompt, mode=mode)


async def _run_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    prompt: str,
    mode: UserMode,
    run_ctx: RunContext,
    *,
    images: tuple[SDKImage, ...] | None = None,
) -> None:
    app: AppContext = context.application.bot_data["app"]
    slot = run_ctx.slot
    repo = run_ctx.repo
    slot_id = slot.id
    app.job_queue.clear_cancel(user_id)

    is_admin = app.settings.is_admin(user_id)
    thinking_display = resolve_thinking_display(
        app.settings.stream_thinking,
        mode,
        is_admin=is_admin,
    )
    preview_chars = app.settings.stream_thinking_preview_chars
    header = build_run_header(mode, repo.alias)
    model_key = await app.users.get_cursor_model_key(
        user_id, default=app.settings.cursor_model
    )
    message, placeholder_anim = await send_placeholder(
        context,
        user_id,
        header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
    )
    renderer = TelegramStreamRenderer(
        message,
        header=header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        placeholder_animation=placeholder_anim,
        thinking_display=thinking_display,
        thinking_preview_chars=preview_chars,
    )

    app.active_runs[user_id] = ActiveRunInfo(
        message_id=message.message_id,
        chat_id=message.chat_id,
    )

    async def on_update(state):
        if app.job_queue.is_cancelled(user_id):
            raise RunCancelled()
        if state.agent_id:
            placeholder_anim.set_extra_lines([agent_cursor_link(state.agent_id)])
            await app.agent_slots.update_cursor_agent(slot_id, state.agent_id)
        if state.run_id:
            await app.agent_slots.set_active_run(slot_id, state.run_id)
            active = app.active_runs.get(user_id)
            if active is not None:
                app.active_runs[user_id] = ActiveRunInfo(
                    message_id=active.message_id,
                    chat_id=active.chat_id,
                    run_id=state.run_id,
                    agent_id=state.agent_id,
                )
        if not state.has_visible_output(thinking_display=thinking_display):
            if state.run_id:
                await placeholder_anim.set_preset("waiting_signal")
            elif state.agent_id:
                await placeholder_anim.set_preset("run_started")
            else:
                await placeholder_anim.set_preset("starting")
        await renderer.update(state)

    memory_block: str | None = None
    if mode in (UserMode.ASK, UserMode.PLAN):
        entries = await app.memory.recall(user_id, repo.id, prompt)
        memory_block = app.memory.format_recall_block(entries) or None

    cursor_model = resolve_cursor_model(model_key)

    try:
        try:
            outcome, new_agent_id = await app.cursor.run_prompt(
                prompt=prompt,
                mode=mode,
                repo=repo,
                model=cursor_model,
                cursor_agent_id=slot.cursor_agent_id,
                on_update=on_update,
                memory_block=memory_block,
                images=images,
            )
        except RunCancelled:
            await app.agent_slots.set_active_run(slot_id, None)
            return

        if new_agent_id:
            await app.agent_slots.update_cursor_agent(slot_id, new_agent_id)
        if outcome.state.run_id:
            await app.agent_slots.set_active_run(slot_id, outcome.state.run_id)

        footer = build_run_footer(
            pr_url=outcome.state.pr_url,
            agent_id=outcome.state.agent_id,
            error_message=outcome.error_message,
            duration_ms=outcome.state.duration_ms,
        )

        from tg_cursor_bot.services.inline_keyboards import post_run_keyboard

        with_retry = bool(outcome.error_message or outcome.status == "error")
        final_mode = await app.users.get_mode(user_id)
        final_model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        await renderer.finalize(
            outcome.state,
            footer=footer,
            reply_markup=post_run_keyboard(
                is_admin=is_admin,
                current=final_mode,
                current_model_key=final_model_key,
                with_retry=with_retry,
            ),
        )

        await app.memory.index_run(
            tg_user_id=user_id,
            repo_id=repo.id,
            prompt=prompt,
            result=outcome.state.final_text or outcome.state.assistant_text or "",
            mode=mode.value,
            run_id=outcome.state.run_id,
            pr_url=outcome.state.pr_url,
            status=outcome.status,
            duration_ms=outcome.state.duration_ms,
        )

        await app.agent_slots.set_active_run(slot_id, None)
    finally:
        app.active_runs.pop(user_id, None)
        await placeholder_anim.stop()
        await renderer.shutdown()
