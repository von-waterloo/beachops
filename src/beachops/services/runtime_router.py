"""Choose cloud vs Windows execution runtime for a job/slot."""

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
    """Resolve runtime with precedence: explicit job → payload → slot → default."""
    if job_runtime not in (None, ""):
        return parse_runtime(job_runtime)

    if job_payload:
        payload_runtime = job_payload.get("runtime")
        if payload_runtime not in (None, ""):
            return parse_runtime(payload_runtime)

    if slot is not None:
        slot_runtime = getattr(slot, "runtime", None)
        if slot_runtime not in (None, ""):
            return parse_runtime(slot_runtime)

    return parse_runtime(default)


def resolve_runtime(
    *,
    slot_runtime: object | None = None,
    payload_runtime: object | None = None,
    default: object | None = "cloud",
) -> AgentRuntime:
    """Prefer explicit job payload, then slot preference, then settings default."""
    if payload_runtime not in (None, ""):
        return parse_runtime(payload_runtime)
    if slot_runtime not in (None, ""):
        return parse_runtime(slot_runtime)
    return parse_runtime(default)
