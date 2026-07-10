"""Shared cancel logic for /cancel and inline button."""

from __future__ import annotations

from dataclasses import dataclass

from beachops.app_context import AppContext
from beachops.domain.cursor_tokens import normalize_cursor_token_key
from beachops.domain.security import JobStatus


@dataclass(frozen=True, slots=True)
class CancelOutcome:
    cancelled_run: bool
    cleared_queue: int
    cancel_requested: bool = False


def cancel_was_successful(
    outcome: CancelOutcome,
    *,
    cleared_forward: bool = False,
    cleared_coalesce: bool = False,
) -> bool:
    """User-facing cancel succeeded if anything was stopped or cleared."""
    return (
        outcome.cancel_requested
        or outcome.cancelled_run
        or outcome.cleared_queue > 0
        or cleared_forward
        or cleared_coalesce
    )


async def cancel_user_work(app: AppContext, user_id: int) -> CancelOutcome:
    cleared_legacy = app.job_queue.clear_pending(user_id)
    app.job_queue.request_cancel(user_id)
    await app.cancel_store.request_cancel(user_id)

    cancelled_queued = await app.jobs.cancel_queued_for_actor(user_id)
    cleared = cleared_legacy + cancelled_queued

    slot = await app.agent_slots.get_active(user_id)
    active = app.active_runs.get(user_id)

    agent_id = (slot.cursor_agent_id if slot else None) or (
        active.agent_id if active else None
    )
    run_id = (slot.active_run_id if slot else None) or (
        active.run_id if active else None
    )

    # Prefer durable job runtime IDs when in-memory state is empty (worker process).
    if (not agent_id or not run_id) and hasattr(app.jobs, "latest_active_for_actor"):
        job = await app.jobs.latest_active_for_actor(user_id)
        if job is not None:
            agent_id = agent_id or job.cursor_agent_id
            run_id = run_id or job.cursor_run_id
            if job.status in {JobStatus.RUNNING, JobStatus.PLANNING}:
                await app.jobs.transition(
                    user_id,
                    job.id,
                    from_statuses=[job.status],
                    to_status=JobStatus.CANCELLED,
                    event_type="user.cancel",
                )

    cancelled_run = False
    if agent_id and run_id:
        token_key = normalize_cursor_token_key(
            slot.cursor_token_key if slot else None
        )
        cancelled_run = await app.cursor.cancel_run(
            agent_id,
            run_id,
            api_key=app.settings.cursor_api_key_for(token_key),
        )

    # User cancel always clears local run binding — even if Cursor API already finished.
    if slot is not None:
        await app.agent_slots.set_active_run(slot.id, None)

    app.active_runs.pop(user_id, None)
    return CancelOutcome(
        cancelled_run=cancelled_run,
        cleared_queue=cleared,
        cancel_requested=True,
    )
