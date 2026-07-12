"""Start a durable cloud run and hand observation to a background task."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from telegram import Bot
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
from beachops.services.status_animation import AnimatedStatus
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
    """Create/follow-up a Cursor run, persist IDs, then observe in background."""
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
    message, placeholder_anim = await send_placeholder(
        context,
        actor_id,
        header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        current_token_key=ui_token_key,
        reply_to_message_id=app.last_user_messages.get(actor_id),
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
            placeholder_anim.set_extra_lines([agent_cursor_link(current.agent_id)])
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
            telegram_message_id=message.message_id,
            telegram_chat_id=message.chat_id,
        )
        await _maybe_append_run_progress(app, job_id, actor_id, current)
        if current.run_id:
            await placeholder_anim.set_preset("waiting_signal")
        elif current.agent_id:
            await placeholder_anim.set_preset("run_started")

    try:
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
    except RunCancelled:
        await placeholder_anim.stop()
        raise
    except Exception:
        await placeholder_anim.stop()
        raise
    finally:
        # Stop placeholder animation; observer owns the message edits next.
        try:
            await placeholder_anim.stop()
        except Exception:
            logger.debug("placeholder stop failed", exc_info=True)

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
        telegram_message_id=message.message_id,
        telegram_chat_id=message.chat_id,
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
