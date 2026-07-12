"""Background observers for Cursor Cloud Agents API v1 runs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from telegram import Bot
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.active_run import ActiveRunInfo
from beachops.domain.models import UserMode
from beachops.domain.security import JobStatus
from beachops.services.cursor_agent import RunOutcome
from beachops.services.cursor_token_ui import token_ui_pair
from beachops.services.inline_keyboards import post_run_keyboard, status_reply_markup
from beachops.services.job_queue import RunCancelled
from beachops.services.run_finalizer import RunFinalizer
from beachops.services.stream_bridge import StreamState
from beachops.services.stream_display import resolve_thinking_display
from beachops.services.telegram_renderer import TelegramStreamRenderer
from beachops.services.ui_copy import agent_cursor_link, build_run_footer, build_run_header

logger = logging.getLogger(__name__)


class RunObserverRegistry:
    """In-process observe tasks so long SSE does not hold ARQ job slots."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    def is_observing(self, job_id: UUID | str) -> bool:
        task = self._tasks.get(str(job_id))
        return task is not None and not task.done()

    async def spawn(self, job_id: UUID, coro) -> None:
        key = str(job_id)
        async with self._lock:
            existing = self._tasks.get(key)
            if existing is not None and not existing.done():
                return

            async def _runner() -> None:
                try:
                    await coro
                except Exception:
                    logger.exception("Observer failed for job %s", job_id)
                finally:
                    async with self._lock:
                        current = self._tasks.get(key)
                        if current is asyncio.current_task():
                            self._tasks.pop(key, None)

            self._tasks[key] = asyncio.create_task(_runner(), name=f"observe:{key}")

    async def cancel(self, job_id: UUID | str) -> None:
        key = str(job_id)
        async with self._lock:
            task = self._tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("observer cancel await failed", exc_info=True)

    async def cancel_all(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def observe_and_finalize(
    *,
    app: AppContext,
    bot: Bot,
    job_id: UUID,
    actor_id: int,
    mode: UserMode,
    prompt: str,
    repo_id: int,
    repo_alias: str,
    agent_id: str,
    run_id: str,
    api_key: str,
    token_key: str,
    message_id: int,
    chat_id: int,
    last_event_id: str | None = None,
) -> None:
    """Attach to an existing Cursor run, stream into Telegram, then finalize."""
    is_admin = app.settings.is_admin(actor_id)
    thinking_display = resolve_thinking_display(
        app.settings.stream_thinking,
        mode,
        is_admin=is_admin,
    )
    model_key = await app.users.get_cursor_model_key(
        actor_id, default=app.settings.cursor_model
    )
    ui_token_key, available_tokens = await token_ui_pair(app, actor_id)
    header = build_run_header(mode, repo_alias)

    # Reconstruct a Message-like handle for the renderer.
    class _MessageProxy:
        def __init__(self) -> None:
            self.chat_id = chat_id
            self.message_id = message_id

        def get_bot(self):
            return bot

        async def edit_text(self, text, **kwargs):
            return await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                **kwargs,
            )

        async def edit_reply_markup(self, **kwargs):
            return await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                **kwargs,
            )

    message = _MessageProxy()
    renderer = TelegramStreamRenderer(
        message,  # type: ignore[arg-type]
        header=header,
        is_admin=is_admin,
        mode=mode,
        current_model_key=model_key,
        current_token_key=ui_token_key,
        available_token_keys=available_tokens,
        thinking_display=thinking_display,
        thinking_preview_chars=app.settings.stream_thinking_preview_chars,
    )
    state = StreamState(agent_id=agent_id, run_id=run_id, last_event_id=last_event_id)
    app.active_runs[actor_id] = ActiveRunInfo(
        message_id=message_id,
        chat_id=chat_id,
        run_id=run_id,
        agent_id=agent_id,
    )
    keep_alive = False

    async def _cancelled() -> bool:
        return app.job_queue.is_cancelled(actor_id) or await app.cancel_store.is_cancelled(
            actor_id
        )

    async def on_update(current: StreamState) -> None:
        if await _cancelled():
            raise RunCancelled()
        if current.agent_id or current.run_id:
            await app.jobs.set_runtime(
                actor_id,
                job_id,
                cursor_agent_id=current.agent_id,
                cursor_run_id=current.run_id,
                cursor_last_event_id=current.last_event_id,
                cursor_run_status=current.status,
                telegram_message_id=message_id,
                telegram_chat_id=chat_id,
            )
        from beachops.services.run_executor import _maybe_append_run_progress

        await _maybe_append_run_progress(app, job_id, actor_id, current)
        if current.agent_id:
            await renderer.update(current)

    try:
        if await _cancelled():
            raise RunCancelled()
        outcome = await app.cursor.observe_run(
            agent_id=agent_id,
            run_id=run_id,
            state=state,
            on_update=on_update,
            api_key=api_key,
            last_event_id=last_event_id,
            plan_mode=mode == UserMode.PLAN,
        )
        # Still running after observe — leave job active for reconciler/respawn.
        if outcome.status in {"", "running", "creating", "in_progress"}:
            logger.warning(
                "Observer paused while job %s still %s — keeping RUNNING",
                job_id,
                outcome.status or "running",
            )
            keep_alive = True
            await renderer.update(outcome.state)
            return
        footer = build_run_footer(
            pr_url=outcome.state.pr_url,
            agent_id=outcome.state.agent_id,
            error_message=outcome.error_message,
            duration_ms=outcome.state.duration_ms,
            total_tokens=outcome.state.total_tokens,
            input_tokens=outcome.state.input_tokens,
            output_tokens=outcome.state.output_tokens,
        )
        final_mode = await app.users.get_mode(actor_id)
        final_model_key = await app.users.get_cursor_model_key(
            actor_id, default=app.settings.cursor_model
        )
        final_token_key, available_tokens = await token_ui_pair(app, actor_id)
        await renderer.finalize(
            outcome.state,
            footer=footer,
            reply_markup=post_run_keyboard(
                is_admin=is_admin,
                current=final_mode,
                current_model_key=final_model_key,
                current_token_key=final_token_key,
                available_token_keys=available_tokens,
                with_retry=bool(outcome.error_message or outcome.status == "error"),
            ),
        )
        await RunFinalizer(app, bot).finalize(
            job_id=job_id,
            actor_id=actor_id,
            mode=mode,
            outcome=outcome,
            prompt=prompt,
            repo_id=repo_id,
        )
    except RunCancelled:
        final_mode = await app.users.get_mode(actor_id)
        final_model_key = await app.users.get_cursor_model_key(
            actor_id, default=app.settings.cursor_model
        )
        final_token_key, available_tokens = await token_ui_pair(app, actor_id)
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
        await app.jobs.transition(
            actor_id,
            job_id,
            from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
            to_status=JobStatus.CANCELLED,
            event_type="observer.cancelled",
        )
        await app.jobs.mark_finalized(actor_id, job_id)
    except Exception:
        logger.exception("Observer crashed for job %s", job_id)
        raise
    finally:
        if not keep_alive:
            app.active_runs.pop(actor_id, None)
            await renderer.shutdown()
            await app.cancel_store.clear_cancel(actor_id)
        else:
            # Soft-stop edits only; cron will respawn a fresh observer.
            await renderer.shutdown()
            app.active_runs.pop(actor_id, None)
