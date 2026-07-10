"""Domain models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UserMode(str, Enum):
    ASK = "ask"
    PLAN = "plan"
    DO = "do"


@dataclass(frozen=True)
class RepoConfig:
    id: int
    tg_user_id: int
    alias: str
    github_url: str
    default_branch: str
    is_active: bool


@dataclass(frozen=True)
class AgentSlot:
    id: int
    tg_user_id: int
    label: str
    cursor_agent_id: str | None
    repo_id: int | None
    active_run_id: str | None
    is_active: bool
    repo_alias: str | None = None
    # Токен (mt/mt2), под которым создан агент Cursor; None — run ещё не было.
    cursor_token_key: str | None = None
    runtime: str = "cloud"
    local_path: str | None = None
    preferred_worker_id: str | None = None


@dataclass(frozen=True)
class RunSummary:
    id: int
    mode: str
    prompt_summary: str
    result_summary: str | None
    pr_url: str | None
    status: str
    duration_ms: int | None
    created_at: str
    cursor_agent_id: str | None
    run_id: str | None


@dataclass(frozen=True)
class MemoryEntry:
    id: int
    kind: str
    title: str
    body: str
    source_prompt: str | None
    mode: str | None
    pr_url: str | None
    status: str | None
    duration_ms: int | None
    created_at: str
    run_id: str | None
    repo_id: int | None
