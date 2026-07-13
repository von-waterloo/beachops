"""observe_run must not finalize while Cursor is still RUNNING."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from beachops.services.cursor_agent import CursorAgentService, _sse_text_payload
from beachops.services.cursor_cloud_client import UsageBreakdown
from beachops.services.stream_bridge import StreamState


@pytest.mark.asyncio
async def test_observe_run_polls_after_bare_done(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CursorAgentService(
        api_key="test",
        model="composer-2.5",
        workspace=Path("."),
    )
    state = StreamState(status="running")
    updates: list[str] = []

    async def on_update(current: StreamState) -> None:
        updates.append(current.status)

    async def fake_consume(**kwargs: Any) -> bool:
        # Simulate SSE closing with bare `done` while still running.
        return False

    snapshots = iter(
        [
            {"status": "running", "result": ""},
            {"status": "running", "result": ""},
            {
                "status": "finished",
                "result": "Готово: починил стрим.",
                "duration_ms": 1200,
            },
        ]
    )

    async def fake_snapshot(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return next(snapshots)

    async def fake_usage(*_args: Any, **_kwargs: Any) -> UsageBreakdown:
        return UsageBreakdown(total_tokens=42, output_tokens=42)

    monkeypatch.setattr(service, "_consume_sse", fake_consume)
    monkeypatch.setattr(service, "get_run_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "fetch_run_usage", fake_usage)
    monkeypatch.setattr(
        "beachops.services.cursor_agent.asyncio.sleep",
        AsyncMock(),
    )

    outcome = await service.observe_run(
        agent_id="bc-1",
        run_id="run-1",
        state=state,
        on_update=on_update,
        max_reconnects=0,
    )
    assert outcome.status == "finished"
    assert outcome.state.final_text == "Готово: починил стрим."
    assert outcome.state.total_tokens == 42
    assert "finished" in updates


@pytest.mark.asyncio
async def test_consume_sse_ignores_parallel_interaction_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """assistant + interaction_update carry the same delta — only one must apply."""
    from beachops.services.cursor_sse import SseEvent

    service = CursorAgentService(
        api_key="test",
        model="composer-2.5",
        workspace=Path("."),
    )
    state = StreamState(status="running")

    events = [
        SseEvent(event="assistant", data={"text": "И"}, id="1"),
        SseEvent(
            event="interaction_update",
            data={"type": "text-delta", "text": "И"},
            id="2",
        ),
        SseEvent(event="assistant", data={"text": "щу"}, id="3"),
        SseEvent(
            event="interaction_update",
            data={"type": "text-delta", "text": "щу"},
            id="4",
        ),
        SseEvent(
            event="result",
            data={"status": "FINISHED", "text": "Ищу"},
            id="5",
        ),
    ]

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def stream_run(self, *_args, **_kwargs):
            for event in events:
                yield event

    monkeypatch.setattr(service, "_client", lambda _api_key=None: _FakeClient())

    terminal = await service._consume_sse(
        agent_id="bc-1",
        run_id="run-1",
        state=state,
        on_update=AsyncMock(),
        api_key="test",
        last_event_id=None,
    )
    assert terminal is True
    assert state.assistant_text == "Ищу"
    assert state.final_text == "Ищу"


@pytest.mark.asyncio
async def test_finalizer_refuses_running_status() -> None:
    from beachops.domain.models import UserMode
    from beachops.services.cursor_agent import RunOutcome
    from beachops.services.run_finalizer import RunFinalizer
    from beachops.services.stream_bridge import StreamState

    app = MagicMock()
    app.jobs.mark_finalized = AsyncMock()
    bot = MagicMock()
    finalizer = RunFinalizer(app, bot)
    ok = await finalizer.finalize(
        job_id=MagicMock(),
        actor_id=1,
        mode=UserMode.DO,
        outcome=RunOutcome(StreamState(status="running"), "running"),
        prompt="x",
        repo_id=1,
    )
    assert ok is False
    app.jobs.mark_finalized.assert_not_awaited()
