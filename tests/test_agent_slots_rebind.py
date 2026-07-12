"""Agent slot repo rebind on /repo switch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from beachops.domain.models import AgentSlot, RepoConfig
from beachops.services.agent_slots import AgentSlotService


def _slot(**kwargs) -> AgentSlot:
    base = dict(
        id=1,
        tg_user_id=42,
        label="Тест",
        cursor_agent_id="agent_abc",
        repo_id=1,
        active_run_id=None,
        is_active=True,
        runtime="cloud",
        local_path=None,
        preferred_worker_id=None,
        cursor_token_key="mt",
        repo_alias="old",
    )
    base.update(kwargs)
    return AgentSlot(**base)


def _repo(**kwargs) -> RepoConfig:
    base = dict(
        id=5,
        tg_user_id=42,
        alias="beachops",
        github_url="https://github.com/you/beachops",
        default_branch="dev",
        is_active=True,
    )
    base.update(kwargs)
    return RepoConfig(**base)


@pytest.mark.asyncio
async def test_sync_active_slot_repo_rebinds_and_clears_agent() -> None:
    slots = AsyncMock()
    repos = AsyncMock()
    settings = SimpleNamespace(agent_slots_max=8, default_branch="dev")
    service = AgentSlotService(slots, repos, settings)

    bound = _slot(repo_id=1, cursor_agent_id="agent_old")
    slots.get_active = AsyncMock(return_value=bound)
    slots.rebind_repo = AsyncMock()

    await service.sync_active_slot_repo(42, _repo(id=5))

    slots.rebind_repo.assert_awaited_once_with(1, 5)


@pytest.mark.asyncio
async def test_sync_active_slot_repo_noop_when_same_repo() -> None:
    slots = AsyncMock()
    repos = AsyncMock()
    settings = SimpleNamespace(agent_slots_max=8, default_branch="dev")
    service = AgentSlotService(slots, repos, settings)

    bound = _slot(repo_id=5, cursor_agent_id="agent_ok")
    slots.get_active = AsyncMock(return_value=bound)
    slots.rebind_repo = AsyncMock()

    await service.sync_active_slot_repo(42, _repo(id=5))

    slots.rebind_repo.assert_not_awaited()
