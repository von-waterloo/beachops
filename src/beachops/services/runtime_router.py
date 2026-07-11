"""Choose execution runtime for a job/slot (cloud-only product surface)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from beachops.domain.models import AgentSlot
from beachops.domain.runtime import AgentRuntime, parse_runtime


def choose_runtime(
    *,
    slot: AgentSlot | None = None,
    job_payload: Mapping[str, Any] | None = None,
    job_runtime: str | None = None,
    default: object | None = "cloud",
) -> AgentRuntime:
    """Always cloud — Windows runtime is removed from the product surface."""
    del slot, job_payload, job_runtime, default
    return AgentRuntime.CLOUD


def resolve_runtime(
    *,
    slot_runtime: object | None = None,
    payload_runtime: object | None = None,
    default: object | None = "cloud",
) -> AgentRuntime:
    """Cloud-only; ignore legacy windows preferences."""
    del slot_runtime, payload_runtime, default
    return AgentRuntime.CLOUD
