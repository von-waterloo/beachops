"""Idempotent terminal finalization for Cursor cloud runs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

from telegram import Bot

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.domain.security import ApprovalKind, JobStatus, Role
from beachops.services.cursor_agent import RunOutcome
from beachops.services.inline_keyboards import job_approval_keyboard
from beachops.services.redaction import redact_text
from beachops.services.stream_bridge import StreamState
from beachops.services.ui_copy import build_run_footer

logger = logging.getLogger(__name__)


class RunFinalizer:
    def __init__(self, app: AppContext, bot: Bot) -> None:
        self._app = app
        self._bot = bot

    async def finalize(
        self,
        *,
        job_id: UUID,
        actor_id: int,
        mode: UserMode,
        outcome: RunOutcome,
        prompt: str,
        repo_id: int,
    ) -> bool:
        """Apply terminal side-effects once. Returns False if already finalized."""
        if outcome.status in {"", "running", "creating", "in_progress"}:
            logger.warning(
                "Refusing to finalize job %s while Cursor status is %s",
                job_id,
                outcome.status or "running",
            )
            return False

        claimed = await self._app.jobs.mark_finalized(actor_id, job_id)
        if not claimed:
            return False

        state = outcome.state
        await self._app.jobs.set_result(
            actor_id,
            job_id,
            pr_url=state.pr_url,
            total_tokens=state.total_tokens,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            cache_read_tokens=state.cache_read_tokens,
            cache_write_tokens=state.cache_write_tokens,
        )
        await self._app.jobs.set_runtime(
            actor_id,
            job_id,
            cursor_agent_id=state.agent_id,
            cursor_run_id=state.run_id,
            cursor_last_event_id=state.last_event_id,
            cursor_run_status=state.status,
        )

        if outcome.status == "finished" and not outcome.error_message:
            try:
                await self._app.memory.index_run(
                    tg_user_id=actor_id,
                    repo_id=repo_id,
                    prompt=prompt,
                    result=state.final_text or state.assistant_text or "",
                    mode=mode.value,
                    run_id=state.run_id,
                    pr_url=state.pr_url,
                    status=outcome.status,
                    duration_ms=state.duration_ms,
                )
            except Exception:
                logger.exception("memory.index_run failed for job %s", job_id)

            try:
                from beachops.services.run_artifacts import deliver_run_artifacts

                await deliver_run_artifacts(
                    self._app,
                    self._bot,
                    job_id=job_id,
                    actor_id=actor_id,
                    agent_id=state.agent_id,
                    mode=mode,
                    state=state,
                )
            except Exception:
                logger.exception("artifact delivery failed for job %s", job_id)

        job = await self._app.jobs.get_internal(job_id)
        if job is None:
            return True

        if mode == UserMode.PLAN and outcome.status == "finished" and not outcome.error_message:
            await self._finalize_plan(job, actor_id)
        elif outcome.status == "cancelled":
            await self._app.jobs.transition(
                actor_id,
                job_id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=JobStatus.CANCELLED,
                event_type="finalizer.cancelled",
            )
        elif outcome.status != "finished" or outcome.error_message:
            await self._app.jobs.transition(
                actor_id,
                job_id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=JobStatus.FAILED,
                event_type="finalizer.failed",
                details={"reason": outcome.error_message or outcome.status},
            )
        else:
            await self._app.jobs.transition(
                actor_id,
                job_id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=JobStatus.SUCCEEDED,
                event_type="finalizer.finished",
            )

        slot = await self._app.agent_slots.get_active(actor_id)
        if slot is not None and slot.active_run_id == state.run_id:
            await self._app.agent_slots.set_active_run(slot.id, None)
        return True

    async def _finalize_plan(self, job, actor_id: int) -> None:
        is_owner_actor = actor_id in {
            *self._app.settings.owner_user_ids,
            *self._app.settings.admin_user_ids,
        }
        if self._app.settings.auto_approve_plans or is_owner_actor:
            await self._app.jobs.transition(
                actor_id,
                job.id,
                from_statuses=[JobStatus.PLANNING, JobStatus.RUNNING],
                to_status=JobStatus.AWAITING_APPROVAL,
                event_type="approval.auto_requested",
                details={"kind": ApprovalKind.PLAN_EXECUTION.value, "auto": True},
            )
            refreshed = await self._app.jobs.get_internal(job.id)
            if refreshed is None:
                return
            from beachops.services.approval_actions import approve_job

            try:
                await approve_job(self._app, refreshed, ApprovalKind.PLAN_EXECUTION)
            except Exception:
                logger.exception("Auto-approve plan failed for %s", job.id)
            return

        approval = await self._app.approvals.create(
            actor_id,
            job.id,
            kind=ApprovalKind.PLAN_EXECUTION,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        if approval is None:
            return
        await self._app.jobs.transition(
            actor_id,
            job.id,
            from_statuses=[JobStatus.PLANNING, JobStatus.RUNNING],
            to_status=JobStatus.AWAITING_APPROVAL,
            event_type="approval.requested",
            details={"kind": ApprovalKind.PLAN_EXECUTION.value},
        )
        owners = tuple(
            dict.fromkeys(
                (*self._app.settings.owner_user_ids, *self._app.settings.admin_user_ids)
            )
        )
        text = "План готов. Подтверди выполнение — или отклони / запроси правки."
        for owner_id in owners:
            await self._app.users.ensure_user(owner_id, True, role=Role.OWNER)
            approve = await self._app.callback_tokens.issue_for_recipient(
                job_owner_id=actor_id,
                recipient_actor_id=owner_id,
                job_id=job.id,
                action="approve",
                ttl_sec=self._app.settings.callback_token_ttl_sec,
            )
            reject = await self._app.callback_tokens.issue_for_recipient(
                job_owner_id=actor_id,
                recipient_actor_id=owner_id,
                job_id=job.id,
                action="reject",
                ttl_sec=self._app.settings.callback_token_ttl_sec,
            )
            await self._bot.send_message(
                chat_id=owner_id,
                text=f"{text}\n\nЗадача: {job.id}\n{job.summary[:500]}",
                reply_markup=job_approval_keyboard(
                    approve_token=approve,
                    reject_token=reject,
                ),
            )


def outcome_from_snapshot(snapshot: dict, state: StreamState | None = None) -> RunOutcome:
    state = state or StreamState()
    state.status = str(snapshot.get("status") or "error")
    state.agent_id = snapshot.get("agent_id") or state.agent_id
    state.run_id = snapshot.get("run_id") or state.run_id
    result = redact_text(str(snapshot.get("result") or ""))
    if result:
        state.final_text = result
        if not state.assistant_text:
            state.assistant_text = result
    if snapshot.get("pr_url"):
        state.pr_url = str(snapshot["pr_url"])
    if snapshot.get("branch_name"):
        state.branch_name = str(snapshot["branch_name"])
    if snapshot.get("duration_ms") is not None:
        state.duration_ms = int(snapshot["duration_ms"])
    if snapshot.get("total_tokens") is not None:
        state.total_tokens = int(snapshot["total_tokens"])
    status = state.status
    if status == "error":
        return RunOutcome(state, status, "Run finished with error status")
    if status == "cancelled":
        return RunOutcome(state, status)
    return RunOutcome(state, status if status else "finished")
