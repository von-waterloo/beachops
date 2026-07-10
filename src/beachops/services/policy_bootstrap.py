"""Build the effective repository allowlist from settings."""

from __future__ import annotations

from beachops.config.settings import Settings
from beachops.services.repository_policy import (
    RepositoryPolicyError,
    RepositoryPolicyService,
)


def build_repository_policy(settings: Settings) -> RepositoryPolicyService:
    """Load ``REPOSITORY_POLICY_JSON`` and optionally merge self-improve repo."""
    policy = RepositoryPolicyService.from_json(settings.repository_policy_json)
    if not settings.self_improve_enabled:
        return policy
    url = settings.self_improve_repo_url_resolved()
    if not url:
        raise RepositoryPolicyError(
            "SELF_IMPROVE_ENABLED requires SELF_IMPROVE_REPO_URL "
            "or GITHUB_REPO (HTTPS GitHub URL of your BeachOps fork)"
        )
    return policy.with_extra_repository(
        repository_url=url,
        allowed_branches=tuple(settings.self_improve_branches),
    )
