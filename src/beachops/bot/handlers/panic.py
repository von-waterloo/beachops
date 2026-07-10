"""Owner-only emergency write lock."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.security import JobKind, JobStatus, RiskLevel, Role
from beachops.services.cancel_service import cancel_user_work
from beachops.services.inline_keyboards import unpanic_keyboard


async def panic_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    if app.settings.role_for(user.id) != Role.OWNER:
        await message.reply_text("Только владелец может включить аварийный режим.")
        return

    await app.system_state.set_panic(
        True,
        actor_id=user.id,
        actor_role=Role.OWNER,
    )
    active_users = tuple(app.active_runs)
    for active_user_id in active_users:
        await cancel_user_work(app, active_user_id)

    jobs = await app.jobs.list_by_status_internal(
        [
            JobStatus.DRAFT,
            JobStatus.QUEUED,
            JobStatus.PLANNING,
            JobStatus.APPROVED,
            JobStatus.RUNNING,
            JobStatus.REVISION_REQUESTED,
        ]
    )
    for job in jobs:
        if job.cursor_agent_id and job.cursor_run_id:
            await app.cursor.cancel_run(job.cursor_agent_id, job.cursor_run_id)
        await app.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[job.status],
            to_status=JobStatus.CANCELLED,
            event_type="panic.cancelled",
        )
    await app.audit.append(
        actor_id=user.id,
        event_type="system.panic",
        action="enable",
        outcome="success",
        details={"cancelled_jobs": len(jobs)},
    )
    await message.reply_text(
        "PANIC включён. Очередь остановлена, активные runs отменяются, "
        "новые write-действия заблокированы."
    )


async def unpanic_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    if app.settings.role_for(user.id) != Role.OWNER:
        await message.reply_text("Только владелец может отключить аварийный режим.")
        return
    if not await app.system_state.is_panic_enabled():
        await message.reply_text("PANIC уже выключен.")
        return

    confirmation = await app.jobs.create(
        user.id,
        kind=JobKind.READ,
        risk_level=RiskLevel.LOW,
        status=JobStatus.DRAFT,
        summary="Подтверждение отключения PANIC",
    )
    token = await app.callback_tokens.issue(
        user.id,
        confirmation.id,
        action="unpanic",
        ttl_sec=app.settings.callback_token_ttl_sec,
    )
    await message.reply_text(
        "Подтвердите повторное включение write-действий.",
        reply_markup=unpanic_keyboard(token),
    )
