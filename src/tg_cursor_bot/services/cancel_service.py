"""Shared cancel logic for /cancel and inline button."""

from __future__ import annotations

from dataclasses import dataclass

from tg_cursor_bot.app_context import AppContext


@dataclass(frozen=True, slots=True)
class CancelOutcome:
    cancelled_run: bool
    cleared_queue: int


async def cancel_user_work(app: AppContext, user_id: int) -> CancelOutcome:
    cleared = app.job_queue.clear_pending(user_id)
    app.job_queue.request_cancel(user_id)
    slot = await app.agent_slots.get_active(user_id)
    active = app.active_runs.get(user_id)

    agent_id = (slot.cursor_agent_id if slot else None) or (
        active.agent_id if active else None
    )
    run_id = (slot.active_run_id if slot else None) or (
        active.run_id if active else None
    )

    cancelled_run = False
    if agent_id and run_id:
        cancelled_run = await app.cursor.cancel_run(agent_id, run_id)
        if cancelled_run and slot is not None:
            await app.agent_slots.set_active_run(slot.id, None)

    app.active_runs.pop(user_id, None)
    return CancelOutcome(cancelled_run=cancelled_run, cleared_queue=cleared)
