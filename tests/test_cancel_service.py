"""Tests for shared cancel logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from beachops.services.cancel_service import (
    CancelOutcome,
    cancel_user_work,
    cancel_was_successful,
)


def test_cancel_was_successful_when_only_requested() -> None:
    outcome = CancelOutcome(cancelled_run=False, cleared_queue=0, cancel_requested=True)
    assert cancel_was_successful(outcome)


def test_cancel_was_successful_with_coalesce() -> None:
    outcome = CancelOutcome(cancelled_run=False, cleared_queue=0, cancel_requested=False)
    assert cancel_was_successful(outcome, cleared_coalesce=True)


@pytest.mark.asyncio
async def test_cancel_user_work_clears_active_run_even_if_api_returns_false() -> None:
    slot = SimpleNamespace(
        id=7,
        cursor_agent_id="bc-agent",
        cursor_token_key="mt",
        active_run_id="run-1",
    )
    app = SimpleNamespace(
        job_queue=SimpleNamespace(
            clear_pending=lambda _uid: 0,
            request_cancel=lambda _uid: None,
        ),
        cancel_store=SimpleNamespace(
            request_cancel=AsyncMock(),
        ),
        jobs=SimpleNamespace(
            list_queued_for_actor=AsyncMock(return_value=[]),
            cancel_queued_for_actor=AsyncMock(return_value=0),
            latest_active_for_actor=AsyncMock(return_value=None),
        ),
        agent_slots=SimpleNamespace(
            get_active=AsyncMock(return_value=slot),
            set_active_run=AsyncMock(),
        ),
        active_runs={42: SimpleNamespace(agent_id="bc-agent", run_id="run-1")},
        cursor=SimpleNamespace(cancel_run=AsyncMock(return_value=False)),
        settings=SimpleNamespace(cursor_api_key_for=lambda _key: "key"),
    )

    outcome = await cancel_user_work(app, 42)  # type: ignore[arg-type]

    assert outcome.cancel_requested is True
    assert outcome.cancelled_run is False
    app.agent_slots.set_active_run.assert_awaited_once_with(7, None)
    assert 42 not in app.active_runs
