"""Usage helpers for Cursor Cloud Agents API v1."""

from __future__ import annotations

from beachops.services.cursor_cloud_client import UsageBreakdown, _usage_from_mapping
from beachops.services.stream_bridge import StreamState


def test_usage_from_mapping_reads_camel_case() -> None:
    usage = _usage_from_mapping(
        {
            "inputTokens": 10,
            "outputTokens": 4,
            "cacheReadTokens": 2,
            "cacheWriteTokens": 1,
            "totalTokens": 17,
        }
    )
    assert usage == UsageBreakdown(
        input_tokens=10,
        output_tokens=4,
        cache_read_tokens=2,
        cache_write_tokens=1,
        total_tokens=17,
    )


def test_stream_state_accepts_usage_fields() -> None:
    state = StreamState()
    state.input_tokens = 11
    state.output_tokens = 3
    state.total_tokens = 14
    assert state.total_tokens == 14
