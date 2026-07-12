"""Run orchestration for text and voice prompts."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.config.settings import Settings
from beachops.domain.active_run import ActiveRunInfo
from beachops.domain.cursor_tokens import normalize_cursor_token_key
from beachops.domain.models import UserMode
from beachops.services.agent_slots import RunContext
from beachops.services.cursor_token_ui import token_ui_pair
from beachops.services.cursor_agent import RunOutcome
from beachops.services.job_queue import RunCancelled, SubmitInfo, SubmitResult
from beachops.services.stream_bridge import StreamState
from beachops.services.stream_display import resolve_thinking_display
from beachops.services.telegram_renderer import TelegramStreamRenderer, send_placeholder
from beachops.services.ui_copy import (
    access_denied_mode,
    agent_cursor_link,
    build_run_footer,
    build_run_header,
    queue_full_message,
    queued_message,
)

try:
    from cursor_sdk import SDKImage
except ImportError:  # pragma: no cover
    SDKImage = object  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

_LAST_PROMPT_TTL_SEC = 600
_PROGRESS_BUCKET_SEC = 3

# Длинный результат урезается в сообщении Telegram (4096 с учётом шапки/футера),
# поэтому сохраняем полный markdown отдельным файлом.
_RESULT_DOCUMENT_THRESHOLD = 3000


async def _self_improve_flag(app: AppContext, repository_url: str) -> bool:
    from beachops.services.self_improve import is_self_improve_active_for

    return await is_self_improve_active_for(app, repository_url)


async def _maybe_append_run_progress(
    app: AppContext,
    job_id,
    actor_id: int,
    state: StreamState,
) -> None:
    """Throttle durable run.progress events for Mini App / voice live feed."""
    text = (
        (state.final_text or state.plan_text or state.assistant_text or "").strip()
    )
    tool = (state.tool_lines[-1] if state.tool_lines else "") or ""
    if not text and not tool:
        return
    bucket = int(time.time()) // _PROGRESS_BUCKET_SEC
    await app.run_events.append(
        job_id=job_id,
        actor_id=actor_id,
        event_type="run.progress",
        payload={
            "assistantText": text[:2000] if text else None,
            "tool": tool[:240] if tool else None,
            "status": state.status,
        },
        idempotency_key=f"{job_id}:progress:{bucket}",
        sequence=bucket,
    )


async def _maybe_send_result_document(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    mode: UserMode,
    state,
) -> None:
    result_text = state.plan_text if mode == UserMode.PLAN else (
        state.final_text or state.assistant_text
    )
    if not result_text or len(result_text) <= _RESULT_DOCUMENT_THRESHOLD:
        return

    if mode == UserMode.PLAN:
        from beachops.services.plan_format import plan_document_filename
        from beachops.services.ui_copy import plan_document_caption

        filename = plan_document_filename(state.plan_name)
        caption = plan_document_caption(state.plan_name)
    else:
        from beachops.services.ui_copy import answer_document_caption

        filename = "cursor_answer.md"
        caption = answer_document_caption()

    try:
        await context.bot.send_document(
            chat_id=user_id,
            document=result_text.encode("utf-8"),
            filename=filename,
            caption=caption,
        )
    except Exception:
        logger.warning("Failed to send full result document", exc_info=True)


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
        from beachops.services.ui_copy import no_repo_selected

        return no_repo_selected()

    from beachops.services.repository_policy import RepositoryNotAllowedError
    from beachops.services.ui_copy import repo_not_allowed

    try:
        app.repository_policy.require_allowed(
            ctx.repo.github_url,
            ctx.repo.default_branch,
            write=mode == UserMode.DO,
        )
    except RepositoryNotAllowedError as exc:
        return repo_not_allowed(str(exc))

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


async def resolve_run_token_key(app: AppContext, user_id: int, slot) -> str:
    """Токен для run: закреплённый за слотом, иначе выбор пользователя.

    Агент Cursor, созданный под одним токеном, нельзя резюмить другим,
    поэтому после первого run токен фиксируется на слоте.
    """
    if slot.cursor_agent_id and slot.cursor_token_key:
        return normalize_cursor_token_key(slot.cursor_token_key)
    token_key = await app.users.get_cursor_token_key(user_id)
    if not app.settings.has_cursor_token(token_key):
        return normalize_cursor_token_key(None)
    return token_key


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
    idempotency_key: str | None = None,
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
    if run_ctx is None:
        return SubmitInfo(SubmitResult.REJECTED)

    remember_prompt(app, user_id, prompt)
    await app.agent_slots.maybe_autoname_active(user_id, prompt)

    if not images:
        from beachops.services.durable_dispatch import dispatch_prompt

        dispatched = await dispatch_prompt(
            app,
            actor_id=user_id,
            prompt=prompt,
            mode=mode,
            run_context=run_ctx,
            idempotency_key=idempotency_key,
        )
        if not dispatched.enqueued:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"BeachOps заблокировал запрос: {dispatched.reason or 'policy'}",
            )
            return SubmitInfo(SubmitResult.REJECTED)
        position = await app.jobs.queue_position(user_id, dispatched.job.id)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"Задача принята · {dispatched.job.id}"
                + (f" · очередь #{position}" if position > 1 else "")
            ),
        )
        return SubmitInfo(
            SubmitResult.QUEUED,
            queue_position=max(1, position),
        )

    image_tuple = tuple(images) if images else None

    async def job() -> None:
        live_ctx = await app.agent_slots.get_run_context(user_id)
        if live_ctx is None:
            await context.bot.send_message(
                chat_id=user_id,
                text=(await validate_prompt_request(app, user_id, mode=mode))
                or "Репозиторий не выбран.",
            )
            return
        await _run_job(context, user_id, prompt, mode, live_ctx, images=image_tuple)

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
    job_id=None,
    channel: str | None = None,
) -> RunOutcome | None:
    from uuid import UUID

    app: AppContext = context.application.bot_data["app"]
    slot = run_ctx.slot
    repo = run_ctx.repo
    slot_id = slot.id
    durable_job_id: UUID | None = job_id if isinstance(job_id, UUID) else (
        UUID(str(job_id)) if job_id else None
    )
    app.job_queue.clear_cancel(user_id)
    await app.cancel_store.clear_cancel(user_id)

    is_admin = app.settings.is_admin(user_id)
    thinking_display = resolve_thinking_display(
        app.settings.stream_thinking,
        mode,
        is_admin=is_admin,
    )
    preview_chars = app.settings.stream_thinking_preview_chars
    header = build_run_header(mode, repo.alias)
    from beachops.services.cursor_model_catalog import resolve_user_model_selection
    from beachops.services.logging_config import bind_log_context

    model_key, cursor_model = await resolve_user_model_selection(app, user_id)
    bind_log_context(
        user_id=user_id,
        job_id=str(durable_job_id) if durable_job_id else None,
        action="run_job",
    )
    token_key = await resolve_run_token_key(app, user_id, slot)
    api_key = app.settings.cursor_api_key_for(token_key)
    ui_token_key, available_tokens = await token_ui_pair(app, user_id)
    message, placeholder_anim = await send_placeholder(
        context,
        user_id,
        header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        current_token_key=ui_token_key,
        reply_to_message_id=app.last_user_messages.get(user_id),
    )
    renderer = TelegramStreamRenderer(
        message,
        header=header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        current_token_key=ui_token_key,
        available_token_keys=available_tokens,
        placeholder_animation=placeholder_anim,
        thinking_display=thinking_display,
        thinking_preview_chars=preview_chars,
    )

    app.active_runs[user_id] = ActiveRunInfo(
        message_id=message.message_id,
        chat_id=message.chat_id,
    )
    if durable_job_id is not None:
        await app.jobs.set_runtime(
            user_id,
            durable_job_id,
            telegram_chat_id=message.chat_id,
            telegram_message_id=message.message_id,
        )

    async def _cancelled() -> bool:
        return app.job_queue.is_cancelled(user_id) or await app.cancel_store.is_cancelled(
            user_id
        )

    async def on_update(state):
        if await _cancelled():
            raise RunCancelled()
        if state.agent_id:
            placeholder_anim.set_extra_lines([agent_cursor_link(state.agent_id)])
            await app.agent_slots.update_cursor_agent(
                slot_id, state.agent_id, token_key=token_key
            )
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
        if durable_job_id is not None and (state.agent_id or state.run_id):
            await app.jobs.set_runtime(
                user_id,
                durable_job_id,
                cursor_agent_id=state.agent_id,
                cursor_run_id=state.run_id,
                telegram_message_id=message.message_id,
                telegram_chat_id=message.chat_id,
            )
        if durable_job_id is not None:
            await _maybe_append_run_progress(app, durable_job_id, user_id, state)
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

    from beachops.services.situation_brief import build_situation_brief

    situation_block = await build_situation_brief(
        app,
        actor_id=user_id,
        run_context=run_ctx,
        role=app.settings.role_for(user_id),
        channel=channel,
    )

    from beachops.services.inline_keyboards import post_run_keyboard, status_reply_markup

    try:
        if await _cancelled():
            raise RunCancelled()

        try:
            outcome, new_agent_id = await app.cursor.run_prompt(
                prompt=prompt,
                mode=mode,
                repo=repo,
                model=cursor_model,
                cursor_agent_id=slot.cursor_agent_id,
                on_update=on_update,
                memory_block=memory_block,
                situation_block=situation_block,
                images=images,
                api_key=api_key,
                self_improve=await _self_improve_flag(app, repo.github_url),
                channel=channel,
            )
        except RunCancelled:
            final_mode = await app.users.get_mode(user_id)
            final_model_key = await app.users.get_cursor_model_key(
                user_id, default=app.settings.cursor_model
            )
            final_token_key, available_tokens = await token_ui_pair(app, user_id)
            await renderer.finalize(
                StreamState(),
                footer="⏹ Отменено",
                reply_markup=status_reply_markup(
                    is_admin=is_admin,
                    current=final_mode,
                    current_model_key=final_model_key,
                    has_repos=True,
                    current_token_key=final_token_key,
                    available_token_keys=available_tokens,
                ),
            )
            return None

        if new_agent_id:
            await app.agent_slots.update_cursor_agent(
                slot_id, new_agent_id, token_key=token_key
            )
        if durable_job_id is not None:
            await app.jobs.set_runtime(
                user_id,
                durable_job_id,
                cursor_agent_id=outcome.state.agent_id or new_agent_id,
                cursor_run_id=outcome.state.run_id,
                cursor_token_key=token_key,
                cursor_last_event_id=outcome.state.last_event_id,
                cursor_run_status=outcome.state.status,
                telegram_message_id=message.message_id,
                telegram_chat_id=message.chat_id,
            )

        footer = build_run_footer(
            pr_url=outcome.state.pr_url,
            agent_id=outcome.state.agent_id,
            error_message=outcome.error_message,
            duration_ms=outcome.state.duration_ms,
            total_tokens=outcome.state.total_tokens,
            input_tokens=outcome.state.input_tokens,
            output_tokens=outcome.state.output_tokens,
        )

        with_retry = bool(outcome.error_message or outcome.status == "error")
        # Durable worker issues owner-bound, single-use approval buttons.
        # Static plan buttons are replayable and therefore never shown.
        with_build_plan = False
        final_mode = await app.users.get_mode(user_id)
        final_model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        final_token_key, available_tokens = await token_ui_pair(app, user_id)
        await renderer.finalize(
            outcome.state,
            footer=footer,
            reply_markup=post_run_keyboard(
                is_admin=is_admin,
                current=final_mode,
                current_model_key=final_model_key,
                current_token_key=final_token_key,
                available_token_keys=available_tokens,
                with_retry=with_retry,
                with_build_plan=with_build_plan,
            ),
        )

        await _maybe_send_result_document(context, user_id, mode, outcome.state)

        if outcome.status == "finished" and not outcome.error_message:
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

        return outcome
    except RunCancelled:
        final_mode = await app.users.get_mode(user_id)
        final_model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        final_token_key, available_tokens = await token_ui_pair(app, user_id)
        await renderer.finalize(
            StreamState(),
            footer="⏹ Отменено",
            reply_markup=status_reply_markup(
                is_admin=is_admin,
                current=final_mode,
                current_model_key=final_model_key,
                has_repos=True,
                current_token_key=final_token_key,
                available_token_keys=available_tokens,
            ),
        )
    except Exception:
        logger.exception("Run job failed for user %s", user_id)
        final_mode = await app.users.get_mode(user_id)
        final_model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        final_token_key, available_tokens = await token_ui_pair(app, user_id)
        await renderer.finalize(
            StreamState(),
            footer="⚠️ Внутренняя ошибка бота",
            reply_markup=post_run_keyboard(
                is_admin=is_admin,
                current=final_mode,
                current_model_key=final_model_key,
                current_token_key=final_token_key,
                available_token_keys=available_tokens,
                with_retry=True,
            ),
        )
    finally:
        # Always clear active run binding — even if finalize/Telegram failed.
        try:
            await app.agent_slots.set_active_run(slot_id, None)
        except Exception:
            logger.debug("active_run cleanup failed", exc_info=True)
        app.active_runs.pop(user_id, None)
        await placeholder_anim.stop()
        await renderer.shutdown()
        await app.cancel_store.clear_cancel(user_id)
    return None
