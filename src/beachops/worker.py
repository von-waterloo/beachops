"""ARQ worker for durable BeachOps Cursor jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

from arq.connections import RedisSettings
from telegram import Bot

from beachops.app_context import AppContext
from beachops.config.settings import get_settings
from beachops.domain.models import UserMode
from beachops.domain.security import ApprovalKind, JobStatus, Role
from beachops.services.inline_keyboards import job_approval_keyboard
from beachops.services.run_executor import _run_job
from beachops.services.run_reconciler import RunReconciler
from beachops.services.notification_notifier import NotificationNotifier

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    from beachops.services.logging_config import configure_logging

    configure_logging(settings.log_level, service="worker")
    app = await AppContext.create(settings)
    bot = Bot(settings.tg_bot_token)
    await bot.initialize()
    ctx["app"] = app
    ctx["bot"] = bot

    # Repair orphaned Telegram/Cursor state before accepting new work.
    try:
        results = await RunReconciler(app).reconcile_stale(bot)
        if results:
            logger.info("Reconciled %s stale jobs on startup", len(results))
    except Exception:
        logger.exception("Startup reconciliation failed")

    # ARQ persists queued jobs. DB rows that were marked running during an
    # unclean restart are safely re-queued as new attempts when Cursor IDs
    # are missing (otherwise reconciler already finalized them).
    stale = await app.jobs.list_by_status_internal(
        [JobStatus.RUNNING, JobStatus.PLANNING]
    )
    for job in stale:
        if job.cursor_agent_id and job.cursor_run_id:
            # Leave for periodic reconciler — Cursor may still be finishing.
            continue
        transitioned = await app.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[job.status],
            to_status=JobStatus.QUEUED,
            event_type="worker.recovered",
        )
        if transitioned:
            await app.arq.enqueue_job("execute_job", str(job.id))


async def shutdown(ctx: dict) -> None:
    bot: Bot | None = ctx.get("bot")
    app: AppContext | None = ctx.get("app")
    if bot is not None:
        await bot.shutdown()
    if app is not None:
        await app.close()


async def execute_job(ctx: dict, job_id: str) -> None:
    app: AppContext = ctx["app"]
    bot: Bot = ctx["bot"]
    job = await app.jobs.get_internal(UUID(job_id))
    if job is None or job.status not in {
        JobStatus.QUEUED,
        JobStatus.APPROVED,
        JobStatus.REVISION_REQUESTED,
    }:
        return

    if await app.cancel_store.is_cancelled(job.actor_id):
        await app.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[job.status],
            to_status=JobStatus.CANCELLED,
            event_type="user.cancel_before_start",
        )
        return

    lock = app.redis.lock(
        f"beachops:actor-lock:{job.actor_id}",
        timeout=7200,
        blocking_timeout=5,
    )
    if not await lock.acquire():
        await app.arq.enqueue_job("execute_job", job_id, _defer_by=5)
        return
    try:
        await _execute_locked(app, bot, job)
    finally:
        await lock.release()


async def reconcile_jobs(ctx: dict) -> None:
    """Periodic cron: finalize jobs + drain Telegram notification outbox."""
    app: AppContext = ctx["app"]
    bot: Bot = ctx["bot"]
    try:
        results = await RunReconciler(app).reconcile_stale(bot)
        if results:
            logger.info("Periodic reconcile actions: %s", len(results))
    except Exception:
        logger.exception("Periodic reconcile failed")
    try:
        sent = await NotificationNotifier(app, bot).drain()
        if sent:
            logger.info("Notifier sent %s outbox items", sent)
    except Exception:
        logger.exception("Notifier drain failed")


async def enqueue_milestone(
    app: AppContext,
    *,
    job_id: UUID,
    actor_id: int,
    event_type: str,
    text: str,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
) -> None:
    """Persist a run event and schedule an idempotent Telegram notification."""
    key = f"{job_id}:{event_type}"
    await app.run_events.append(
        job_id=job_id,
        actor_id=actor_id,
        event_type=event_type,
        payload={"text": text},
        idempotency_key=key,
    )
    await app.notification_outbox.enqueue(
        job_id=job_id,
        actor_id=actor_id,
        kind="edit" if telegram_message_id else "send",
        payload={"text": text},
        idempotency_key=f"notify:{key}",
        telegram_chat_id=telegram_chat_id or actor_id,
        telegram_message_id=telegram_message_id,
    )


async def _execute_locked(app: AppContext, bot: Bot, job) -> None:
    payload = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
    try:
        mode = UserMode(str(payload["mode"]))
        prompt = str(payload["prompt"])
    except (KeyError, ValueError) as exc:
        await _fail_job(app, job, "invalid encrypted payload")
        raise RuntimeError("invalid job payload") from exc

    from beachops.services.telegram_images import decode_payload_images

    try:
        images = decode_payload_images(payload.get("images"))
    except Exception:
        images = []

    run_context = await app.agent_slots.get_run_context(job.actor_id)
    if run_context is None:
        await _fail_job(app, job, "repository context is unavailable")
        await bot.send_message(
            chat_id=job.actor_id,
            text="BeachOps: репозиторий или агент для задачи больше не доступен.",
        )
        return

    target_status = JobStatus.PLANNING if mode == UserMode.PLAN else JobStatus.RUNNING
    transitioned = await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[job.status],
        to_status=target_status,
        event_type="worker.started",
        details={"mode": mode.value},
    )
    if transitioned is None:
        return

    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"app": app}),
        bot=bot,
    )
    from beachops.services.logging_config import bind_log_context, clear_log_context

    bind_log_context(
        job_id=str(job.id),
        user_id=job.actor_id,
        action="execute_job",
    )
    try:
        outcome = await _run_job(
            context,
            job.actor_id,
            prompt,
            mode,
            run_context,
            job_id=job.id,
            images=tuple(images) if images else None,
        )
    finally:
        clear_log_context()
        bind_log_context(service="worker")
    refreshed = await app.jobs.get_internal(job.id)
    if refreshed is not None:
        await enqueue_milestone(
            app,
            job_id=job.id,
            actor_id=job.actor_id,
            event_type="worker.observation_done",
            text=(
                "BeachOps: агент завершил работу."
                if outcome and outcome.status == "finished" and not outcome.error_message
                else "BeachOps: наблюдение за run завершилось — сверяю статус."
            ),
            telegram_chat_id=refreshed.telegram_chat_id,
            telegram_message_id=refreshed.telegram_message_id,
        )
    if outcome is None or outcome.status != "finished" or outcome.error_message:
        # If Cursor IDs were persisted, leave job for reconciler instead of
        # permanently failing a run that may still finish in the cloud.
        refreshed = await app.jobs.get_internal(job.id)
        if (
            refreshed is not None
            and refreshed.cursor_agent_id
            and refreshed.cursor_run_id
            and refreshed.status in {JobStatus.RUNNING, JobStatus.PLANNING}
        ):
            logger.warning(
                "Run observation failed for job %s; leaving for reconciler",
                job.id,
            )
            return
        await _fail_job(
            app, transitioned, outcome.error_message if outcome else "run failed"
        )
        return

    await app.jobs.set_runtime(
        job.actor_id,
        job.id,
        cursor_agent_id=outcome.state.agent_id,
        cursor_run_id=outcome.state.run_id,
    )
    await app.jobs.set_result(
        job.actor_id,
        job.id,
        pr_url=outcome.state.pr_url,
        total_tokens=outcome.state.total_tokens,
    )

    if mode == UserMode.PLAN:
        if app.settings.auto_approve_plans:
            await app.jobs.transition(
                job.actor_id,
                job.id,
                from_statuses=[JobStatus.PLANNING],
                to_status=JobStatus.AWAITING_APPROVAL,
                event_type="approval.auto_requested",
                details={"kind": ApprovalKind.PLAN_EXECUTION.value, "auto": True},
            )
            refreshed = await app.jobs.get_internal(job.id)
            if refreshed is None:
                await _fail_job(app, job, "job missing after plan")
                return
            from beachops.services.approval_actions import approve_job

            try:
                await approve_job(app, refreshed, ApprovalKind.PLAN_EXECUTION)
            except Exception as exc:
                logger.exception(
                    "Auto-approve plan failed",
                    extra={"job_id": str(job.id), "action": "auto_approve"},
                )
                await _fail_job(app, refreshed, f"auto-approve failed: {exc}")
                return
            logger.info(
                "Plan auto-approved into DO",
                extra={"job_id": str(job.id), "action": "auto_approve"},
            )
        else:
            await _request_owner_review(
                app,
                bot,
                job,
                current_status=JobStatus.PLANNING,
                approval_kind=ApprovalKind.PLAN_EXECUTION,
                target_status=JobStatus.AWAITING_APPROVAL,
                text="BeachOps подготовил план. Выполнение требует подтверждения владельца.",
            )
    else:
        await app.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[JobStatus.RUNNING],
            to_status=JobStatus.SUCCEEDED,
            event_type="worker.finished",
        )


async def _request_owner_review(
    app: AppContext,
    bot: Bot,
    job,
    *,
    current_status: JobStatus,
    approval_kind: ApprovalKind,
    target_status: JobStatus,
    text: str,
    revision: bool = False,
) -> None:
    approval = await app.approvals.create(
        job.actor_id,
        job.id,
        kind=approval_kind,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    if approval is None:
        await _fail_job(app, job, "approval could not be created")
        return
    await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[current_status],
        to_status=target_status,
        event_type="approval.requested",
        details={"kind": approval_kind.value},
    )

    owners = tuple(
        dict.fromkeys((*app.settings.owner_user_ids, *app.settings.admin_user_ids))
    )
    for owner_id in owners:
        await app.users.ensure_user(owner_id, True, role=Role.OWNER)
        approve = await app.callback_tokens.issue_for_recipient(
            job_owner_id=job.actor_id,
            recipient_actor_id=owner_id,
            job_id=job.id,
            action="approve",
            ttl_sec=app.settings.callback_token_ttl_sec,
        )
        reject = await app.callback_tokens.issue_for_recipient(
            job_owner_id=job.actor_id,
            recipient_actor_id=owner_id,
            job_id=job.id,
            action="reject",
            ttl_sec=app.settings.callback_token_ttl_sec,
        )
        revision_token = None
        if revision:
            revision_token = await app.callback_tokens.issue_for_recipient(
                job_owner_id=job.actor_id,
                recipient_actor_id=owner_id,
                job_id=job.id,
                action="revision",
                ttl_sec=app.settings.callback_token_ttl_sec,
            )
        await bot.send_message(
            chat_id=owner_id,
            text=f"{text}\n\nЗадача: {job.id}\n{job.summary[:500]}",
            reply_markup=job_approval_keyboard(
                approve_token=approve,
                reject_token=reject,
                revision_token=revision_token,
            ),
        )


async def _fail_job(app: AppContext, job, reason: str | None) -> None:
    await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[
            JobStatus.QUEUED,
            JobStatus.PLANNING,
            JobStatus.RUNNING,
            JobStatus.APPROVED,
            JobStatus.REVISION_REQUESTED,
        ],
        to_status=JobStatus.FAILED,
        event_type="worker.failed",
        details={"reason": reason or "unknown"},
    )


try:
    from arq.cron import cron

    _CRON_JOBS = [cron(reconcile_jobs, second={0, 30})]
except Exception:  # pragma: no cover
    _CRON_JOBS = []


class WorkerSettings:
    functions = [execute_job, reconcile_jobs]
    cron_jobs = _CRON_JOBS
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 7200
    max_tries = 1
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
