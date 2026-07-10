"""In-memory tracking of active agent runs per user."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActiveRunInfo:
    message_id: int
    chat_id: int
    run_id: str | None = None
    agent_id: str | None = None
