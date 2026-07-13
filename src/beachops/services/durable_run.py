"""Start a durable cloud run and hand observation to a background task."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from telegram import Bot
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.active_run import ActiveRunInfo
from beachops.domain.models import UserMode
from beachops.domain.prompts import build_prompt, is_protected_default_branch
from beachops.services.agent_slots import RunContext
from beachops.services.cursor_model_catalog import resolve_user_model_selection
from beachops.services.cursor_token_ui import token_ui_pair
from beachops.services.job_queue import RunCancelled
from beachops.services.run_executor import (
    _maybe_append_run_progress,
    _self_improve_flag,
    resolve_run_token_key,
)
from beachops.services.run_observer import observe_and_finalize
from beachops.services.stream_bridge import StreamState
from beachops.services.stream_display import resolve_thinking_display
from beachops.services.telegram_renderer import send_placeholder
from beachops.services.ui_copy import agent_cursor_link, build_run_header

logger = logging.getLogger(__name__)


async def launch_durable_cloud_job(
    *,
    app: AppContext,
    bot: Bot,
    context: ContextTypes.DEFAULT_TYPE,
    job_id: UUID,
    actor_id: int,
    prompt: str,
    mode: UserMode,
    run_ctx: RunContext,
    images: Sequence[Any] | None = None,
    channel: str | None = None,
    observers,
) -> None:
    """Create/follow-up a Cursor run, persist IDs, then observe in background.

    Cursor is started *before* the Telegram placeholder so a Telegram flood
    cannot prevent the cloud agent from receiving the task.
    """
    slot = run_ctx.slot
    repo = run_ctx.repo
    slot_id = slot.id
    app.job_queue.clear_cancel(actor_id)
    await app.cancel_store.clear_cancel(actor_id)

    is_admin = app.settings.is_admin(actor_id)
    thinking_display = resolve_thinking_display(
        app.settings.stream_thinking,
        mode,
        is_admin=is_admin,
    )
    del thinking_display  # used by observer later
    header = build_run_header(mode, repo.alias, channel=channel)
    model_key, cursor_model = await resolve_user_model_selection(app, actor_id)
    token_key = await resolve_run_token_key(app, actor_id, slot)
    api_key = app.settings.cursor_api_key_for(token_key)
    ui_token_key, _available = await token_ui_pair(app, actor_id)

    memory_block: str | None = None
    if mode in (UserMode.ASK, UserMode.PLAN):
        entries = await app.memory.recall(actor_id, repo.id, prompt)
        memory_block = app.memory.format_recall_block(entries) or None

    from beachops.services.situation_brief import build_situation_brief

    situation_block = await build_situation_brief(
        app,
        actor_id=actor_id,
        run_context=run_ctx,
        role=app.settings.role_for(actor_id),
        channel=channel,
    )
    cursor_mode = "agent" if mode in (UserMode.ASK, UserMode.DO) else "plan"
    protected_base = is_protected_default_branch(repo.default_branch)
    work_on_current_branch = mode == UserMode.DO and not protected_base
    auto_create_pr = mode == UserMode.DO and protected_base
    full_prompt = build_prompt(
        prompt,
        mode,
        default_branch=repo.default_branch,
        memory_block=memory_block,
        situation_block=situation_block,
        self_improve=await _self_improve_flag(app, repo.github_url),
        channel=channel,
    )
    state = StreamState()

    async def on_update(current: StreamState) -> None:
        if app.job_queue.is_cancelled(actor_id) or await app.cancel_store.is_cancelled(
            actor_id
        ):
            raise RunCancelled()
        if current.agent_id:
            await app.agent_slots.update_cursor_agent(
                slot_id, current.agent_id, token_key=token_key
            )
        if current.run_id:
            await app.agent_slots.set_active_run(slot_id, current.run_id)
        await app.jobs.set_runtime(
            actor_id,
            job_id,
            cursor_agent_id=current.agent_id,
            cursor_run_id=current.run_id,
            cursor_token_key=token_key,
            cursor_last_event_id=current.last_event_id,
            cursor_run_status=current.status,
        )
        await _maybe_append_run_progress(app, job_id, actor_id, current)

    started = await app.cursor.start_run(
        prompt=full_prompt,
        mode=cursor_mode,
        repo=repo,
        model=cursor_model,
        cursor_agent_id=slot.cursor_agent_id,
        images=images,
        api_key=api_key,
        auto_create_pr=auto_create_pr,
        work_on_current_branch=work_on_current_branch,
        on_update=on_update,
        state=state,
    )

    await app.agent_slots.update_cursor_agent(
        slot_id, started.agent_id, token_key=token_key
    )
    await app.jobs.set_runtime(
        actor_id,
        job_id,
        cursor_agent_id=started.agent_id,
        cursor_run_id=started.run_id,
        cursor_token_key=token_key,
        cursor_run_status=started.state.status,
    )

    message = await _ensure_run_message(
        context,
        actor_id,
        header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        current_token_key=ui_token_key,
        reply_to_message_id=app.last_user_messages.get(actor_id),
        agent_id=started.agent_id,
    )
    app.active_runs[actor_id] = ActiveRunInfo(
        message_id=message.message_id,
        chat_id=message.chat_id,
    )
    await app.jobs.set_runtime(
        actor_id,
        job_id,
        telegram_chat_id=message.chat_id,
        telegram_message_id=message.message_id,
        cursor_token_key=token_key,
    )

    await observers.spawn(
        job_id,
        observe_and_finalize(
            app=app,
            bot=bot,
            job_id=job_id,
            actor_id=actor_id,
            mode=mode,
            prompt=prompt,
            repo_id=repo.id,
            repo_alias=repo.alias,
            agent_id=started.agent_id,
            run_id=started.run_id,
            api_key=api_key,
            token_key=token_key,
            message_id=message.message_id,
            chat_id=message.chat_id,
            last_event_id=started.state.last_event_id,
        ),
    )


async def _ensure_run_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    header: str,
    *,
    is_admin: bool,
    mode: UserMode,
    current_model_key: str,
    current_token_key: str | None,
    reply_to_message_id: int | None,
    agent_id: str | None,
):
    """Create the Telegram run card after Cursor is already running."""
    try:
        message, animation = await _send_placeholder_resilient(
            context,
            chat_id,
            header,
            is_admin=is_admin,
            mode=mode,
            current_model_key=current_model_key,
            current_token_key=current_token_key,
            reply_to_message_id=reply_to_message_id,
            agent_id=agent_id,
        )
        try:
            await animation.stop()
        except Exception:
            logger.debug("placeholder stop failed", exc_info=True)
        return message
    except Exception:
        logger.warning(
            "Animated placeholder failed after Cursor start; sending plain status",
            exc_info=True,
        )

    from beachops.services.inline_keyboards import run_activity_keyboard
    from beachops.services.status_animation import initial_status_text

    lines = [header]
    if agent_id:
        lines.append(agent_cursor_link(agent_id))
    text = "\n".join(lines) + "\n\n" + initial_status_text(preset="run_started")
    # Never delete or edit the user's message — only send a new bot card.
    for attempt in range(4):
        try:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text[:4096],
                reply_markup=run_activity_keyboard(
                    is_admin=is_admin,
                    current=mode,
                    current_model_key=current_model_key,
                    current_token_key=current_token_key,
                ),
                reply_to_message_id=reply_to_message_id,
            )
        except RetryAfter as exc:
            await asyncio.sleep(max(float(exc.retry_after), 1.0) + attempt)
    # Last resort without reply_to to avoid cascading BadRequest.
    return await context.bot.send_message(
        chat_id=chat_id,
        text=text[:4096],
        reply_markup=run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=current_model_key,
            current_token_key=current_token_key,
        ),
    )


async def _send_placeholder_resilient(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    header: str,
    *,
    is_admin: bool,
    mode: UserMode,
    current_model_key: str,
    current_token_key: str | None,
    reply_to_message_id: int | None,
    agent_id: str | None,
    attempts: int = 4,
):
    """Send the Telegram run card; honor flood-control RetryAfter."""
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            message, animation = await send_placeholder(
                context,
                chat_id,
                header,
                is_admin=is_admin,
                mode=mode,
                current_model_key=current_model_key,
                current_token_key=current_token_key,
                reply_to_message_id=reply_to_message_id,
            )
            if agent_id:
                animation.set_extra_lines([agent_cursor_link(agent_id)])
                await animation.set_preset("run_started")
            return message, animation
        except RetryAfter as exc:
            last_exc = exc
            delay = max(float(exc.retry_after), 1.0) + attempt
            logger.warning(
                "Telegram flood on placeholder (attempt %s/%s); sleep %.1ss",
                attempt + 1,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
