from __future__ import annotations

from beachops.services.cursor_cloud_client import CursorCloudError, is_agent_gone_error


def test_is_agent_gone_error_by_code() -> None:
    assert is_agent_gone_error(
        CursorCloudError("missing", status_code=404, code="agent_not_found")
    )
    assert is_agent_gone_error(
        CursorCloudError("missing", status_code=404, code="not_found")
    )


def test_is_agent_gone_error_by_message() -> None:
    assert is_agent_gone_error(CursorCloudError("Agent not found", status_code=404))
    assert not is_agent_gone_error(CursorCloudError("rate limited", status_code=429))
