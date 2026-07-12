"""Tests for Cursor SSE helpers."""

from __future__ import annotations

import pytest

from beachops.services.cursor_sse import (
    extract_git_fields,
    iter_sse_blocks,
    normalize_run_status,
    parse_sse_stream,
)


def test_iter_sse_blocks_keeps_incomplete_tail() -> None:
    events, leftover = iter_sse_blocks(
        "id: 1\nevent: assistant\ndata: {\"text\":\"hi\"}\n\nid: 2\nevent: status\ndata: {\"status\":\"RUNNING\"}"
    )
    assert len(events) == 1
    assert events[0][0] == "assistant"
    assert events[0][1] == "1"
    assert leftover.startswith("id: 2")


def test_normalize_run_status_maps_cursor_values() -> None:
    assert normalize_run_status("FINISHED") == "finished"
    assert normalize_run_status("CREATING") == "running"
    assert normalize_run_status("ERROR") == "error"
    assert normalize_run_status("CANCELLED") == "cancelled"


def test_extract_git_fields_from_nested_git() -> None:
    branch, pr = extract_git_fields(
        {
            "git": {
                "branches": [
                    {
                        "branch": "feat/x",
                        "prUrl": "https://example/pr/1",
                    }
                ]
            }
        }
    )
    assert branch == "feat/x"
    assert pr == "https://example/pr/1"


@pytest.mark.asyncio
async def test_parse_sse_stream_yields_typed_events() -> None:
    async def chunks():
        yield b'id: a1\nevent: assistant\ndata: {"text":"hello"}\n\n'
        yield b'event: done\ndata: {}\n\n'

    events = [event async for event in parse_sse_stream(chunks())]
    assert events[0].id == "a1"
    assert events[0].event == "assistant"
    assert events[0].data["text"] == "hello"
    assert events[1].event == "done"
