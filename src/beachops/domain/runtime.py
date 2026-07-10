"""Agent execution runtime (cloud vs Windows local)."""

from __future__ import annotations

from enum import Enum


class AgentRuntime(str, Enum):
    CLOUD = "cloud"
    WINDOWS = "windows"


def is_cloud_agent_id(agent_id: str | None) -> bool:
    """Cursor cloud agent IDs are prefixed with ``bc-``."""
    if not agent_id:
        return False
    return agent_id.startswith("bc-")


def parse_runtime(value: object | None) -> AgentRuntime:
    if value is None or value == "":
        return AgentRuntime.CLOUD
    text = str(value).strip().lower()
    if text in {"windows", "local", "win"}:
        return AgentRuntime.WINDOWS
    return AgentRuntime.CLOUD
