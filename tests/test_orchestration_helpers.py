"""Tests for runtime router and deploy trigger helpers."""

from __future__ import annotations

import pytest

from beachops.domain.runtime import AgentRuntime, is_cloud_agent_id, parse_runtime
from beachops.services.deploy_trigger import DeployTriggerError, DeployTriggerService
from beachops.services.runtime_router import resolve_runtime


def test_parse_runtime_windows_aliases() -> None:
    assert parse_runtime("windows") is AgentRuntime.WINDOWS
    assert parse_runtime("local") is AgentRuntime.WINDOWS
    assert parse_runtime("cloud") is AgentRuntime.CLOUD
    assert is_cloud_agent_id("bc-abc") is True
    assert is_cloud_agent_id("local-1") is False


def test_resolve_runtime_prefers_payload() -> None:
    assert (
        resolve_runtime(slot_runtime="cloud", payload_runtime="windows")
        is AgentRuntime.WINDOWS
    )
    assert resolve_runtime(slot_runtime="windows", payload_runtime=None) is AgentRuntime.WINDOWS


@pytest.mark.asyncio
async def test_deploy_trigger_rejects_short_sha() -> None:
    service = DeployTriggerService(token="x", repository="von-waterloo/beachops")
    with pytest.raises(DeployTriggerError):
        await service.dispatch_prod_deploy(sha="abc")
    await service.close()
