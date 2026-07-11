"""Strict repository allowlist behavior."""

import pytest

from beachops.services.repository_policy import (
    RepositoryNotAllowedError,
    RepositoryPolicyError,
    RepositoryPolicyService,
    normalize_github_url,
)


def _policy() -> RepositoryPolicyService:
    return RepositoryPolicyService.from_json(
        """
        {
          "repositories": [
            {
              "url": "https://github.com/Acme/BeachOps.git",
              "branches": ["dev", "main"]
            }
          ]
        }
        """
    )


def test_normalizes_exact_github_repository_urls() -> None:
    assert (
        normalize_github_url("git@github.com:Acme/BeachOps.git")
        == "https://github.com/acme/beachops"
    )
    assert (
        normalize_github_url("https://github.com/Acme/BeachOps/")
        == "https://github.com/acme/beachops"
    )


def test_allows_only_exact_repo_and_branch() -> None:
    policy = _policy()

    assert policy.is_allowed("https://github.com/acme/beachops", "dev")
    assert not policy.is_allowed("https://github.com/acme/beachops-extra", "dev")
    assert not policy.is_allowed("https://github.com/acme/beachops", "Dev")

    with pytest.raises(RepositoryNotAllowedError, match="не в списке разрешённых"):
        policy.require_allowed("https://github.com/acme/other", "dev")
    with pytest.raises(RepositoryNotAllowedError, match="не разрешена"):
        policy.require_allowed("https://github.com/acme/beachops", "feature")


def test_to_public_dict_reports_open_and_allowlist() -> None:
    open_policy = RepositoryPolicyService.from_json('{"repositories":[]}')
    assert open_policy.to_public_dict() == {
        "openMode": True,
        "repositories": [],
    }

    strict = _policy()
    payload = strict.to_public_dict()
    assert payload["openMode"] is False
    assert payload["repositories"] == [
        {
            "url": "https://github.com/acme/beachops",
            "branches": ["dev", "main"],
        }
    ]


def test_empty_policy_is_open_mode() -> None:
    policy = RepositoryPolicyService.from_json('{"repositories":[]}')
    assert policy.open_mode is True
    assert policy.is_allowed("https://github.com/acme/app", "dev")
    policy.require_allowed("https://github.com/acme/app", "dev", write=True)
    with pytest.raises(RepositoryNotAllowedError, match="защищённую ветку"):
        policy.require_allowed("https://github.com/acme/app", "main", write=True)


def test_open_mode_survives_extra_repository_merge() -> None:
    policy = RepositoryPolicyService.from_json('{"repositories":[]}')
    merged = policy.with_extra_repository(
        repository_url="https://github.com/acme/beachops",
        allowed_branches=("dev",),
    )
    assert merged.open_mode is True
    assert merged.is_allowed("https://github.com/other/app", "feat/x")


def test_protected_branches_are_readable_but_not_writable() -> None:
    policy = _policy()

    policy.require_allowed("https://github.com/acme/beachops", "main")
    with pytest.raises(RepositoryNotAllowedError, match="защищённую ветку"):
        policy.require_allowed(
            "https://github.com/acme/beachops",
            "main",
            write=True,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/acme/beachops",
        "https://github.example/acme/beachops",
        "https://github.com/acme/beachops/tree/main",
        "https://github.com/acme/beachops?tab=readme",
    ],
)
def test_rejects_non_exact_or_non_github_urls(url: str) -> None:
    with pytest.raises(RepositoryPolicyError):
        normalize_github_url(url)

