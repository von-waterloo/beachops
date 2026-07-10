from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from beachops.services.cursor_agent import CursorAgentService
from beachops.services.stream_bridge import StreamState


async def test_usage_stream_event_updates_cumulative_state() -> None:
    service = CursorAgentService(api_key="test", model="auto", workspace=Path("."))
    state = StreamState()
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=40,
        cache_read_tokens=20,
        cache_write_tokens=5,
        total_tokens=165,
        reasoning_tokens=7,
    )
    updates: list[int | None] = []

    async def on_update(current: StreamState) -> None:
        updates.append(current.total_tokens)

    await service._consume_message(
        SimpleNamespace(type="usage", usage=usage),
        state,
        on_update,
    )

    assert state.total_tokens == 165
    assert state.reasoning_tokens == 7
    assert updates == [165]
