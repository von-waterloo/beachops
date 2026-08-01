from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from beachops.domain.security import Job, JobKind, JobStatus, RiskLevel
from beachops.services.run_reconciler import RunReconciler


def _failed_job(*, finalized_at=None) -> Job:
    return Job(
        id=uuid4(),
        actor_id=1,
        kind=JobKind.ASK,
        status=JobStatus.FAILED,
        risk_level=RiskLevel.LOW,
        summary="test",
        cursor_agent_id="bc-gone",
        cursor_run_id="run-gone",
        finalized_at=finalized_at,
    )


@pytest.mark.asyncio
async def test_reconcile_failed_job_with_gone_agent_marks_finalized() -> None:
    app = MagicMock()
    app.jobs.mark_finalized = AsyncMock(return_value=True)
    app.payload_crypto.decrypt_json = MagicMock(return_value={})
    app.cursor.fetch_run_usage = AsyncMock(return_value=None)

    reconciler = RunReconciler(app)
    reconciler._fetch_run = AsyncMock(  # type: ignore[method-assign]
        return_value={"status": "error", "gone": True, "result": ""}
    )

    result = await reconciler.reconcile_job(MagicMock(), _failed_job())

    assert result is not None
    assert result.action == "failed_closed"
    app.jobs.mark_finalized.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_failed_job_with_success_still_finalizes() -> None:
    app = MagicMock()
    app.jobs.mark_finalized = AsyncMock(return_value=True)
    app.jobs.set_result = AsyncMock()
    app.jobs.set_runtime = AsyncMock()
    app.jobs.get_internal = AsyncMock(return_value=_failed_job())
    app.jobs.transition = AsyncMock()
    app.agent_slots.get_active = AsyncMock(return_value=None)
    app.agent_slots.get_run_context = AsyncMock(return_value=None)
    app.payload_crypto.decrypt_json = MagicMock(return_value={"mode": "ask", "prompt": "hi"})
    app.cursor.fetch_run_usage = AsyncMock(return_value=None)
    app.memory.index_run = AsyncMock()

    reconciler = RunReconciler(app)
    reconciler._fetch_run = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "status": "finished",
            "result": "done",
            "pr_url": None,
            "branch_name": None,
            "duration_ms": None,
        }
    )

    result = await reconciler.reconcile_job(MagicMock(), _failed_job())

    assert result is not None
    assert result.action == "finalized"
    app.jobs.mark_finalized.assert_awaited()
