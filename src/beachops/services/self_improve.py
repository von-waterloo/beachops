"""Resolve whether BeachOps self-improve mode is active for a run."""

from __future__ import annotations

from beachops.app_context import AppContext
from beachops.services.repository_policy import (
    RepositoryPolicyError,
    normalize_github_url,
)


async def resolve_self_improve_state(app: AppContext) -> dict:
    """Effective self-improve flag + target URL for dashboard / API."""
    env_url = app.settings.self_improve_repo_normalized()
    state = await app.system_state.get("self_improve")
    state_url = None
    if state and state.get("repoUrl"):
        try:
            state_url = normalize_github_url(str(state["repoUrl"]))
        except RepositoryPolicyError:
            state_url = None
    target = env_url or state_url
    if state is None:
        # Legacy: env SELF_IMPROVE_ENABLED seeds the first-run default.
        enabled = bool(app.settings.self_improve_enabled and target)
    else:
        enabled = bool(state.get("enabled")) and bool(target)
    return {
        "enabled": enabled,
        "repoUrl": target,
        "branches": list(app.settings.self_improve_branches),
        "canToggle": True,
        "needsRepo": target is None,
    }


async def is_self_improve_active_for(app: AppContext, repository_url: str) -> bool:
    snapshot = await resolve_self_improve_state(app)
    if not snapshot["enabled"] or not snapshot["repoUrl"]:
        return False
    try:
        return normalize_github_url(repository_url) == snapshot["repoUrl"]
    except RepositoryPolicyError:
        return False
