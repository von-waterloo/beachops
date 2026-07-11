"""Build the effective repository allowlist from settings."""

from __future__ import annotations

from beachops.config.settings import Settings
from beachops.services.repository_policy import (
    RepositoryPolicyError,
    RepositoryPolicyService,
)


def build_repository_policy(settings: Settings) -> RepositoryPolicyService:
    """Load ``REPOSITORY_POLICY_JSON`` and optionally merge self-improve repo.

    If ``SELF_IMPROVE_REPO_URL`` is set, the fork is allowlisted so the Mini App
    toggle can turn self-improve on without a process restart. The runtime
    toggle (system_state) still gates whether runs get self-improve prompts.
    """
    policy = RepositoryPolicyService.from_json(settings.repository_policy_json)
    url = settings.self_improve_repo_url.strip()
    if not url:
        if settings.self_improve_enabled:
            raise RepositoryPolicyError(
                "SELF_IMPROVE_ENABLED requires SELF_IMPROVE_REPO_URL "
                "(HTTPS GitHub URL of your BeachOps fork)"
            )
        return policy
    return policy.with_extra_repository(
        repository_url=url,
        allowed_branches=tuple(settings.self_improve_branches),
    )
