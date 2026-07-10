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


def _settings(**kwargs: object) -> SimpleNamespace:
    base = {
        "repository_policy_json": '{"repositories":[]}',
        "self_improve_enabled": False,
        "self_improve_repo_url": "",
        "self_improve_branches": ["dev"],
        "github_repo": "",
    }
    base.update(kwargs)
    settings = SimpleNamespace(**base)

    def resolved() -> str:
        raw = str(settings.self_improve_repo_url).strip()
        if raw:
            return raw
        github_repo = str(settings.github_repo).strip().removesuffix(".git").strip("/")
        if github_repo.count("/") == 1:
            return f"https://github.com/{github_repo}"
        return ""

    settings.self_improve_repo_url_resolved = resolved  # type: ignore[attr-defined]
    return settings


def test_self_improve_off_leaves_policy_unchanged() -> None:
    policy = build_repository_policy(
        _settings(
            self_improve_enabled=False,
            self_improve_repo_url="https://github.com/acme/beachops",
        )
    )
    assert policy.policies == ()


def test_self_improve_merges_fork_into_allowlist() -> None:
    policy = build_repository_policy(
        _settings(
            self_improve_enabled=True,
            self_improve_repo_url="https://github.com/Acme/BeachOps",
            self_improve_branches=["dev", "feat/x"],
        )
    )
    assert policy.open_mode is True
    assert policy.is_allowed("https://github.com/acme/beachops", "dev")
    assert policy.is_allowed("https://github.com/acme/beachops", "feat/x")
    assert policy.is_allowed("https://github.com/other/app", "dev")
    with pytest.raises(RepositoryNotAllowedError):
        policy.require_allowed(
            "https://github.com/acme/beachops",
            "main",
            write=True,
        )


def test_self_improve_uses_github_repo_fallback() -> None:
    policy = build_repository_policy(
        _settings(
            self_improve_enabled=True,
            self_improve_repo_url="",
            github_repo="von-waterloo/beachops",
            self_improve_branches=["dev"],
        )
    )
    assert policy.is_allowed("https://github.com/von-waterloo/beachops", "dev")


def test_self_improve_enabled_without_url_fails_closed() -> None:
    with pytest.raises(RepositoryPolicyError):
        build_repository_policy(
            _settings(
                self_improve_enabled=True,
                self_improve_repo_url="",
                github_repo="",
            )
        )


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
