"""Strict GitHub repository and branch allowlist enforcement."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from beachops.domain.security import RepositoryPolicy

_GITHUB_PATH_RE = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_SCP_RE = re.compile(
    r"^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


class RepositoryPolicyError(ValueError):
    pass


class RepositoryNotAllowedError(PermissionError):
    pass


class RepositoryPolicyService:
    def __init__(self, policies: tuple[RepositoryPolicy, ...]) -> None:
        by_url: dict[str, RepositoryPolicy] = {}
        for policy in policies:
            normalized_url = normalize_github_url(policy.repository_url)
            branches = tuple(_validate_branch(branch) for branch in policy.allowed_branches)
            if not branches:
                raise RepositoryPolicyError(
                    f"repository {normalized_url} must allow at least one branch"
                )
            if len(set(branches)) != len(branches):
                raise RepositoryPolicyError(f"duplicate branch for {normalized_url}")
            if normalized_url in by_url:
                raise RepositoryPolicyError(f"duplicate repository {normalized_url}")
            protected = tuple(
                dict.fromkeys(
                    _validate_branch(branch)
                    for branch in (*policy.protected_branches, "main", "master")
                )
            )
            by_url[normalized_url] = RepositoryPolicy(
                repository_url=normalized_url,
                allowed_branches=branches,
                protected_branches=protected,
            )
        self._by_url = by_url

    @classmethod
    def from_json(cls, raw: str) -> RepositoryPolicyService:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise RepositoryPolicyError("REPOSITORY_POLICY_JSON is invalid JSON") from exc
        if not isinstance(data, Mapping):
            raise RepositoryPolicyError("repository policy must be a JSON object")
        repositories = data.get("repositories", data.get("allowed_repositories", []))
        return cls(_parse_repositories(repositories))

    @property
    def policies(self) -> tuple[RepositoryPolicy, ...]:
        return tuple(self._by_url.values())

    def policy_for(self, repository_url: str) -> RepositoryPolicy | None:
        try:
            normalized = normalize_github_url(repository_url)
        except RepositoryPolicyError:
            return None
        return self._by_url.get(normalized)

    def is_allowed(self, repository_url: str, branch: str) -> bool:
        policy = self.policy_for(repository_url)
        return policy is not None and branch in policy.allowed_branches

    def is_protected(self, repository_url: str, branch: str) -> bool:
        policy = self.policy_for(repository_url)
        return policy is not None and branch in policy.protected_branches

    def require_allowed(
        self,
        repository_url: str,
        branch: str,
        *,
        write: bool = False,
    ) -> RepositoryPolicy:
        policy = self.policy_for(repository_url)
        if policy is None or branch not in policy.allowed_branches:
            raise RepositoryNotAllowedError("repository or branch is not allowlisted")
        if write and branch in policy.protected_branches:
            raise RepositoryNotAllowedError("writes to protected branches are not allowed")
        return policy


def normalize_github_url(repository_url: str) -> str:
    value = repository_url.strip()
    scp_match = _SCP_RE.fullmatch(value)
    if scp_match:
        owner, repository = scp_match.groups()
        return _canonical(owner, repository)

    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RepositoryPolicyError("only exact HTTPS or git@ GitHub repository URLs are allowed")
    match = _GITHUB_PATH_RE.fullmatch(parsed.path)
    if not match:
        raise RepositoryPolicyError("GitHub URL must identify exactly one repository")
    return _canonical(*match.groups())


def _canonical(owner: str, repository: str) -> str:
    if owner in {".", ".."} or repository in {".", ".."}:
        raise RepositoryPolicyError("invalid GitHub repository URL")
    return f"https://github.com/{owner.lower()}/{repository.lower()}"


def _validate_branch(branch: str) -> str:
    value = branch.strip()
    if (
        not value
        or value != branch
        or value.startswith(("/", "."))
        or value.endswith(("/", ".", ".lock"))
        or ".." in value
        or "@{" in value
        or "//" in value
        or any(char.isspace() or char in "~^:?*[\\" for char in value)
    ):
        raise RepositoryPolicyError(f"invalid branch name: {branch!r}")
    return value


def _parse_repositories(value: object) -> tuple[RepositoryPolicy, ...]:
    entries: list[RepositoryPolicy] = []
    if isinstance(value, Mapping):
        iterable = [
            {"url": url, **(spec if isinstance(spec, Mapping) else {"branches": spec})}
            for url, spec in value.items()
        ]
    elif isinstance(value, list):
        iterable = value
    else:
        raise RepositoryPolicyError("repositories must be an object or array")

    for item in iterable:
        if not isinstance(item, Mapping):
            raise RepositoryPolicyError("repository entries must be objects")
        url = item.get("url", item.get("repository_url"))
        branches = item.get("branches", item.get("allowed_branches"))
        protected = item.get("protected_branches", ("main", "master"))
        if not isinstance(url, str) or not isinstance(branches, list):
            raise RepositoryPolicyError("each repository requires url and branches")
        if not all(isinstance(branch, str) for branch in branches):
            raise RepositoryPolicyError("branches must contain only strings")
        if not isinstance(protected, (list, tuple)) or not all(
            isinstance(branch, str) for branch in protected
        ):
            raise RepositoryPolicyError("protected_branches must contain only strings")
        entries.append(
            RepositoryPolicy(
                repository_url=url,
                allowed_branches=tuple(branches),
                protected_branches=tuple(protected),
            )
        )
    return tuple(entries)

