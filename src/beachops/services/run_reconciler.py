"""Reconcile Cursor run state with BeachOps jobs and Telegram UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from telegram import Bot
from telegram.error import BadRequest, NetworkError, TimedOut

from beachops.app_context import AppContext
from beachops.domain.security import Job, JobStatus
from beachops.services.redaction import redact_text
from beachops.services.ui_copy import build_run_footer

logger = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = (
    JobStatus.RUNNING,
    JobStatus.PLANNING,
)
_RECOVERABLE_STATUSES = (
    JobStatus.RUNNING,
    JobStatus.PLANNING,
    JobStatus.FAILED,
)


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    job_id: UUID
    action: str
    detail: str = ""


class RunReconciler:
    """Poll Cursor for terminal status and repair orphaned Telegram messages."""

    def __init__(self, app: AppContext) -> None:
        self._app = app

    async def reconcile_stale(self, bot: Bot, *, limit: int = 50) -> list[ReconcileResult]:
        jobs = await self._app.jobs.list_by_status_internal(
            list(_RECOVERABLE_STATUSES),
            limit=limit,
        )
        results: list[ReconcileResult] = []
        for job in jobs:
            if not job.cursor_agent_id or not job.cursor_run_id:
                continue
            try:
                result = await self.reconcile_job(bot, job)
            except Exception:
                logger.exception("Reconcile failed for job %s", job.id)
                continue
            if result is not None:
                results.append(result)
        return results

    async def reconcile_job(self, bot: Bot, job: Job) -> ReconcileResult | None:
        run_info = await self._fetch_run(job)
        if run_info is None:
            return None

        status = str(run_info.get("status") or "").lower()
        if status in {"", "running", "in_progress"}:
            return ReconcileResult(job.id, "still_running")

        final_text = redact_text(str(run_info.get("result") or ""))
        pr_url = run_info.get("pr_url")
        total_tokens = run_info.get("total_tokens")
        error = status == "error"

        if job.status in _ACTIVE_JOB_STATUSES or (
            job.status == JobStatus.FAILED and status in {"finished", "completed", "cancelled"}
        ):
            target = JobStatus.FAILED if error else JobStatus.SUCCEEDED
            if status == "cancelled":
                target = JobStatus.CANCELLED
            await self._app.jobs.set_result(
                job.actor_id,
                job.id,
                pr_url=str(pr_url) if pr_url else None,
                total_tokens=int(total_tokens) if total_tokens is not None else None,
            )
            await self._app.jobs.transition(
                job.actor_id,
                job.id,
                from_statuses=[job.status],
                to_status=target,
                event_type="reconciler.terminal",
                details={"cursor_status": status},
            )
            await self._patch_telegram(
                bot,
                job,
                final_text=final_text,
                status=status,
                pr_url=str(pr_url) if pr_url else None,
                error=error,
            )
            slot = await self._app.agent_slots.get_active(job.actor_id)
            if slot is not None and slot.active_run_id == job.cursor_run_id:
                await self._app.agent_slots.set_active_run(slot.id, None)
            return ReconcileResult(job.id, "finalized", status)

        return ReconcileResult(job.id, "noop", status)

    async def _fetch_run(self, job: Job) -> dict[str, Any] | None:
        assert job.cursor_agent_id and job.cursor_run_id
        try:
            return await self._app.cursor.get_run_snapshot(
                job.cursor_agent_id,
                job.cursor_run_id,
            )
        except Exception:
            logger.warning(
                "Could not fetch Cursor run %s for job %s",
                job.cursor_run_id,
                job.id,
                exc_info=True,
            )
            return None

    async def _patch_telegram(
        self,
        bot: Bot,
        job: Job,
        *,
        final_text: str,
        status: str,
        pr_url: str | None,
        error: bool,
    ) -> None:
        chat_id = job.telegram_chat_id or job.actor_id
        message_id = job.telegram_message_id
        footer = build_run_footer(
            pr_url=pr_url,
            agent_id=job.cursor_agent_id,
            error_message="Run finished with error" if error else None,
        )
        body = (final_text or "").strip() or f"Статус Cursor: {status}"
        text = f"BeachOps · reconciled\n\n{body}"
        if footer:
            text = f"{text}\n\n{footer}"
        if len(text) > 4096:
            text = text[:4090] + "…"

        try:
            if message_id is not None:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                )
            else:
                sent = await bot.send_message(chat_id=chat_id, text=text)
                await self._app.jobs.set_runtime(
                    job.actor_id,
                    job.id,
                    telegram_message_id=sent.message_id,
                )
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.warning("Reconcile Telegram edit failed: %s", exc)
        except (TimedOut, NetworkError):
            logger.warning("Reconcile Telegram network error", exc_info=True)
        except Exception:
            logger.warning("Reconcile Telegram update failed", exc_info=True)
