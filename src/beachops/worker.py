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
from beachops.domain.security import JobStatus
from beachops.services.run_observer import RunObserverRegistry, observe_and_finalize
from beachops.services.run_reconciler import RunReconciler
from beachops.services.notification_notifier import NotificationNotifier
from beachops.services.durable_run import launch_durable_cloud_job

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    from beachops.services.logging_config import configure_logging

    configure_logging(settings.log_level, service="worker")
    app = await AppContext.create(settings)
    bot = Bot(settings.tg_bot_token)
    await bot.initialize()
    observers = RunObserverRegistry()
    ctx["app"] = app
    ctx["bot"] = bot
    ctx["observers"] = observers

    try:
        results = await RunReconciler(app).reconcile_stale(bot)
        if results:
            logger.info("Reconciled %s stale jobs on startup", len(results))
    except Exception:
        logger.exception("Startup reconciliation failed")

    # Re-attach observers for cloud runs that already have Cursor IDs.
    active = await app.jobs.list_by_status_internal(
        [JobStatus.RUNNING, JobStatus.PLANNING]
    )
    for job in active:
        if not job.cursor_agent_id or not job.cursor_run_id:
            transitioned = await app.jobs.transition(
                job.actor_id,
                job.id,
                from_statuses=[job.status],
                to_status=JobStatus.QUEUED,
                event_type="worker.recovered",
            )
            if transitioned:
                await app.arq.enqueue_job("execute_job", str(job.id))
            continue
        if observers.is_observing(job.id):
            continue
        token_key = job.cursor_token_key
        api_key = app.settings.cursor_api_key_for(token_key)
        if job.telegram_message_id is None:
            continue
        try:
            from beachops.services.stream_bridge import normalize_run_status

            snapshot = await app.cursor.get_run_snapshot(
                job.cursor_agent_id,
                job.cursor_run_id,
                api_key=api_key,
            )
            status = normalize_run_status(str(snapshot.get("status") or ""))
            if status in {"finished", "error", "cancelled", "completed"}:
                result = await RunReconciler(app).reconcile_job(bot, job)
                if result:
                    logger.info(
                        "Rehydrate finalized job %s (%s)",
                        job.id,
                        result.action,
                    )
                continue
        except Exception:
            logger.debug(
                "Rehydrate pre-check failed for job %s; attaching observer",
                job.id,
                exc_info=True,
            )
        payload = {}
        try:
            payload = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
        except Exception:
            logger.warning("Could not decrypt payload for rehydrate %s", job.id)
        mode = UserMode.ASK
        prompt = job.summary or ""
        try:
            mode = UserMode(str(payload.get("mode") or "ask"))
            prompt = str(payload.get("prompt") or prompt)
        except ValueError:
            pass
        run_ctx = await app.agent_slots.get_run_context(job.actor_id)
        repo_id = run_ctx.repo.id if run_ctx else 0
        repo_alias = run_ctx.repo.alias if run_ctx else "repo"
        await observers.spawn(
            job.id,
            observe_and_finalize(
                app=app,
                bot=bot,
                job_id=job.id,
                actor_id=job.actor_id,
                mode=mode,
                prompt=prompt,
                repo_id=repo_id,
                repo_alias=repo_alias,
                agent_id=job.cursor_agent_id,
                run_id=job.cursor_run_id,
                api_key=api_key,
                token_key=token_key or "mt",
                message_id=job.telegram_message_id,
                chat_id=job.telegram_chat_id or job.actor_id,
                last_event_id=job.cursor_last_event_id,
            ),
        )


async def shutdown(ctx: dict) -> None:
    observers: RunObserverRegistry | None = ctx.get("observers")
    if observers is not None:
        await observers.cancel_all()
    bot: Bot | None = ctx.get("bot")
    app: AppContext | None = ctx.get("app")
    if bot is not None:
        await bot.shutdown()
    if app is not None:
        await app.close()


async def execute_job(ctx: dict, job_id: str) -> None:
    app: AppContext = ctx["app"]
    bot: Bot = ctx["bot"]
    observers: RunObserverRegistry = ctx["observers"]
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

    # Busy-gate: another cloud run for this actor is still in flight.
    active = await app.jobs.latest_active_for_actor(job.actor_id)
    if (
        active is not None
        and active.id != job.id
        and active.cursor_agent_id
        and active.cursor_run_id
        and active.finalized_at is None
    ):
        # Zombie RUNNING jobs (Cursor agent gone) block the whole queue forever.
        # Fail stale blockers so deferred queued jobs can start.
        stamp = active.updated_at or active.created_at
        age = datetime.now(timezone.utc) - stamp if stamp is not None else timedelta(0)
        if age >= timedelta(minutes=20):
            logger.warning(
                "Failing stale active job %s (age=%ss) to unblock queue",
                active.id,
                int(age.total_seconds()),
                extra={
                    "job_id": str(active.id),
                    "action": "worker_zombie_timeout",
                    "actor_id": job.actor_id,
                },
            )
            await app.jobs.transition(
                active.actor_id,
                active.id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=JobStatus.FAILED,
                event_type="worker.zombie_timeout",
                details={"reason": "stale active run blocked queue"},
            )
            await app.jobs.mark_finalized(active.actor_id, active.id)
        else:
            await app.arq.enqueue_job("execute_job", job_id, _defer_by=5)
            return

    lock = app.redis.lock(
        f"beachops:actor-lock:{job.actor_id}",
        timeout=120,
        blocking_timeout=5,
    )
    if not await lock.acquire():
        await app.arq.enqueue_job("execute_job", job_id, _defer_by=5)
        return
    try:
        await _execute_locked(app, bot, job, observers)
    finally:
        await lock.release()


async def reconcile_jobs(ctx: dict) -> None:
    """Periodic cron: finalize jobs + drain Telegram notification outbox."""
    app: AppContext = ctx["app"]
    bot: Bot = ctx["bot"]
    observers: RunObserverRegistry = ctx.get("observers") or RunObserverRegistry()
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
    try:
        from beachops.services.agent_cloud_reconciler import AgentCloudReconciler

        drift = await AgentCloudReconciler(app).sync_linked_slots()
        if drift:
            logger.info("Agent cloud sync notes: %s", len(drift))
    except Exception:
        logger.exception("Agent cloud sync failed")

    # Ensure observers exist for any active jobs missing an in-process task.
    active = await app.jobs.list_by_status_internal(
        [JobStatus.RUNNING, JobStatus.PLANNING], limit=50
    )
    for job in active:
        if not job.cursor_agent_id or not job.cursor_run_id:
            continue
        if observers.is_observing(job.id):
            continue
        if job.telegram_message_id is None or job.finalized_at is not None:
            continue
        token_key = job.cursor_token_key
        api_key = app.settings.cursor_api_key_for(token_key)
        payload: dict = {}
        try:
            payload = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
        except Exception:
            logger.warning("Could not decrypt payload for observer respawn %s", job.id)
        mode = UserMode.ASK
        prompt = job.summary or ""
        try:
            mode = UserMode(str(payload.get("mode") or "ask"))
            prompt = str(payload.get("prompt") or prompt)
        except ValueError:
            pass
        run_ctx = await app.agent_slots.get_run_context(job.actor_id)
        repo_id = run_ctx.repo.id if run_ctx else 0
        repo_alias = run_ctx.repo.alias if run_ctx else "repo"
        logger.info("Respawning observer for job %s", job.id)
        await observers.spawn(
            job.id,
            observe_and_finalize(
                app=app,
                bot=bot,
                job_id=job.id,
                actor_id=job.actor_id,
                mode=mode,
                prompt=prompt,
                repo_id=repo_id,
                repo_alias=repo_alias,
                agent_id=job.cursor_agent_id,
                run_id=job.cursor_run_id,
                api_key=api_key,
                token_key=token_key or "mt",
                message_id=job.telegram_message_id,
                chat_id=job.telegram_chat_id or job.actor_id,
                last_event_id=job.cursor_last_event_id,
            ),
        )


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


async def _execute_locked(
    app: AppContext,
    bot: Bot,
    job,
    observers: RunObserverRegistry,
) -> None:
    payload = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
    try:
        mode = UserMode(str(payload["mode"]))
        prompt = str(payload["prompt"])
    except (KeyError, ValueError) as exc:
        await _fail_job(app, job, "invalid encrypted payload")
        raise RuntimeError("invalid job payload") from exc

    from beachops.services.telegram_images import decode_payload_images

    channel = str(payload.get("channel") or "").strip().lower() or None
    try:
        images = decode_payload_images(payload.get("images"))
    except Exception:
        images = []

    run_context = await app.agent_slots.get_run_context(job.actor_id)
    if run_context is None:
        await _fail_job(app, job, "repository context is unavailable")
        await bot.send_message(
            chat_id=job.actor_id,
            text="Репозиторий или агент для задачи больше не доступен.",
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
        await launch_durable_cloud_job(
            app=app,
            bot=bot,
            context=context,
            job_id=job.id,
            actor_id=job.actor_id,
            prompt=prompt,
            mode=mode,
            run_ctx=run_context,
            images=tuple(images) if images else None,
            channel=channel,
            observers=observers,
        )
    except Exception as exc:
        logger.exception("Failed to launch durable job %s", job.id)
        refreshed = await app.jobs.get_internal(job.id)
        if (
            refreshed is not None
            and refreshed.cursor_agent_id
            and refreshed.cursor_run_id
            and refreshed.status in {JobStatus.RUNNING, JobStatus.PLANNING}
        ):
            logger.warning(
                "Launch observation failed for job %s; leaving for reconciler",
                job.id,
            )
            return
        # Telegram flood must not kill a job that never reached Cursor UI —
        # and if Cursor IDs exist we already returned above. Re-queue briefly.
        reason = str(exc)
        if "Flood control" in reason or "Retry in" in reason or "RetryAfter" in type(exc).__name__:
            logger.warning(
                "Telegram flood launching job %s; requeue in 15s",
                job.id,
            )
            # Roll status back to queued so execute_job will pick it up again.
            await app.jobs.transition(
                transitioned.actor_id,
                transitioned.id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=JobStatus.QUEUED,
                event_type="worker.requeue_flood",
                details={"reason": reason},
            )
            await app.arq.enqueue_job("execute_job", str(job.id), _defer_by=15)
            return
        await _fail_job(app, transitioned, reason)
    finally:
        clear_log_context()
        bind_log_context(service="worker")


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

    _CRON_JOBS = [
        cron(reconcile_jobs, second={0, 30}),
    ]
except Exception:  # pragma: no cover
    _CRON_JOBS = []


class WorkerSettings:
    functions = [execute_job, reconcile_jobs]
    cron_jobs = _CRON_JOBS
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 8
    job_timeout = 300
    max_tries = 1
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
