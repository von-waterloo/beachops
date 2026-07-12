"""Reconcile Cursor run state with BeachOps jobs and Telegram UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from telegram import Bot

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.domain.security import Job, JobStatus
from beachops.services.cursor_agent import RunOutcome
from beachops.services.run_finalizer import RunFinalizer
from beachops.services.stream_bridge import StreamState

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
            if getattr(job, "finalized_at", None) is not None:
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
        if status in {"", "running", "creating", "in_progress"}:
            return ReconcileResult(job.id, "still_running")

        if job.status not in _ACTIVE_JOB_STATUSES and not (
            job.status == JobStatus.FAILED
            and status in {"finished", "completed", "cancelled"}
        ):
            return ReconcileResult(job.id, "noop", status)

        payload: dict[str, Any] = {}
        try:
            if job.payload_ciphertext:
                payload = self._app.payload_crypto.decrypt_json(job.payload_ciphertext)
        except Exception:
            logger.warning("Could not decrypt payload for reconcile %s", job.id)

        mode = UserMode.ASK
        prompt = job.summary or ""
        try:
            mode = UserMode(str(payload.get("mode") or "ask"))
            prompt = str(payload.get("prompt") or prompt)
        except ValueError:
            pass

        state = StreamState(
            status=status,
            agent_id=job.cursor_agent_id,
            run_id=job.cursor_run_id,
            final_text=str(run_info.get("result") or "") or None,
            assistant_text=str(run_info.get("result") or ""),
            pr_url=str(run_info["pr_url"]) if run_info.get("pr_url") else None,
            branch_name=str(run_info["branch_name"])
            if run_info.get("branch_name")
            else None,
            duration_ms=run_info.get("duration_ms"),
            last_event_id=job.cursor_last_event_id,
        )
        usage = await self._app.cursor.fetch_run_usage(
            job.cursor_agent_id,
            job.cursor_run_id,
            api_key=self._app.settings.cursor_api_key_for(job.cursor_token_key),
        )
        if usage is not None:
            state.input_tokens = usage.input_tokens
            state.output_tokens = usage.output_tokens
            state.cache_read_tokens = usage.cache_read_tokens
            state.cache_write_tokens = usage.cache_write_tokens
            state.total_tokens = usage.total_tokens

        error_message = (
            "Run finished with error"
            if status == "error"
            else None
        )
        outcome = RunOutcome(state, status, error_message)
        run_ctx = await self._app.agent_slots.get_run_context(job.actor_id)
        repo_id = run_ctx.repo.id if run_ctx else 0
        finalized = await RunFinalizer(self._app, bot).finalize(
            job_id=job.id,
            actor_id=job.actor_id,
            mode=mode,
            outcome=outcome,
            prompt=prompt,
            repo_id=repo_id,
        )
        if not finalized:
            return ReconcileResult(job.id, "already_finalized", status)
        return ReconcileResult(job.id, "finalized", status)

    async def _fetch_run(self, job: Job) -> dict[str, Any] | None:
        assert job.cursor_agent_id and job.cursor_run_id
        try:
            return await self._app.cursor.get_run_snapshot(
                job.cursor_agent_id,
                job.cursor_run_id,
                api_key=self._app.settings.cursor_api_key_for(job.cursor_token_key),
            )
        except Exception:
            logger.warning(
                "Could not fetch Cursor run %s for job %s",
                job.cursor_run_id,
                job.id,
                exc_info=True,
            )
            return None
