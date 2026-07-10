"""Self-improve policy merge and deploy history."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from beachops.domain.prompts import SELF_IMPROVE_SAFETY, build_prompt
from beachops.domain.models import UserMode
from beachops.services.deploy_history import DeployHistory
from beachops.services.policy_bootstrap import build_repository_policy
from beachops.services.repository_policy import (
    RepositoryNotAllowedError,
    RepositoryPolicyError,
)


def test_self_improve_off_leaves_policy_unchanged() -> None:
    settings = SimpleNamespace(
        repository_policy_json='{"repositories":[]}',
        self_improve_enabled=False,
        self_improve_repo_url="https://github.com/acme/beachops",
        self_improve_branches=["dev"],
    )
    policy = build_repository_policy(settings)
    assert policy.policies == ()


def test_self_improve_merges_fork_into_allowlist() -> None:
    settings = SimpleNamespace(
        repository_policy_json='{"repositories":[]}',
        self_improve_enabled=True,
        self_improve_repo_url="https://github.com/Acme/BeachOps",
        self_improve_branches=["dev", "feat/x"],
    )
    policy = build_repository_policy(settings)
    assert policy.is_allowed("https://github.com/acme/beachops", "dev")
    assert policy.is_allowed("https://github.com/acme/beachops", "feat/x")
    with pytest.raises(RepositoryNotAllowedError):
        policy.require_allowed(
            "https://github.com/acme/beachops",
            "main",
            write=True,
        )


def test_self_improve_enabled_without_url_fails_closed() -> None:
    settings = SimpleNamespace(
        repository_policy_json='{"repositories":[]}',
        self_improve_enabled=True,
        self_improve_repo_url="",
        self_improve_branches=["dev"],
    )
    with pytest.raises(RepositoryPolicyError):
        build_repository_policy(settings)


def test_self_improve_prompt_guards_owner_access() -> None:
    prompt = build_prompt("улучши auth", UserMode.DO, self_improve=True)
    assert SELF_IMPROVE_SAFETY.strip() in prompt
    assert "OWNER_USER_IDS" in prompt
    assert "Passkey" in prompt


@pytest.mark.asyncio
async def test_deploy_history_previous_skips_tip() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.items: list[bytes] = []

        async def lpush(self, key: str, value: bytes) -> int:
            self.items.insert(0, value)
            return len(self.items)

        async def ltrim(self, key: str, start: int, end: int) -> bool:
            self.items = self.items[start : end + 1]
            return True

        async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
            return self.items[start : end + 1]

    history = DeployHistory(FakeRedis())  # type: ignore[arg-type]
    await history.record(sha="aaa", ref="main")
    await history.record(sha="bbb", ref="main")
    assert await history.previous_sha(current_hint="bbb") == "aaa"
    assert await history.previous_sha(current_hint="zzz") == "bbb"
