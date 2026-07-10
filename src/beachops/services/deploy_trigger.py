"""Trigger GitHub Actions deploy-prod via workflow_dispatch (owner approval only)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class DeployTriggerError(ValueError):
    pass


@dataclass(frozen=True)
class DeployDispatchResult:
    repository: str
    workflow: str
    ref: str
    sha: str


def _parse_repo(repository: str) -> tuple[str, str]:
    parts = [part for part in repository.strip().strip("/").split("/") if part]
    if len(parts) != 2:
        raise DeployTriggerError("GITHUB_REPO must be owner/name")
    return parts[0], parts[1]


class DeployTriggerService:
    """Calls Actions workflow_dispatch for deploy-prod.yml with a fixed commit SHA.

    Intended for the owner-approval path only: the bot must never hold SSH keys;
    deploy runs on the self-hosted runner after this API call.
    """

    def __init__(
        self,
        *,
        token: str,
        repository: str,
        workflow: str = "deploy-prod.yml",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token.strip():
            raise DeployTriggerError("GITHUB_TOKEN is required for deploy dispatch")
        self._owner, self._repo = _parse_repo(repository)
        self._workflow = workflow.strip() or "deploy-prod.yml"
        self._client = client or httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token.strip()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def dispatch_prod_deploy(
        self,
        *,
        sha: str,
        ref: str = "main",
    ) -> DeployDispatchResult:
        commit = sha.strip()
        if not commit or len(commit) < 7:
            raise DeployTriggerError("deploy sha is required")
        branch_or_tag = ref.strip() or "main"

        response = await self._client.post(
            f"/repos/{self._owner}/{self._repo}/actions/workflows/{self._workflow}/dispatches",
            json={
                "ref": branch_or_tag,
                "inputs": {"sha": commit},
            },
        )
        if response.status_code == 404:
            raise DeployTriggerError(
                "workflow or repository not found (check GITHUB_REPO and workflow file)"
            )
        if response.status_code == 422:
            detail = response.text[:300]
            raise DeployTriggerError(f"workflow_dispatch rejected: {detail}")
        if response.status_code not in {204, 200}:
            raise DeployTriggerError(
                f"workflow_dispatch failed HTTP {response.status_code}: {response.text[:300]}"
            )

        return DeployDispatchResult(
            repository=f"{self._owner}/{self._repo}",
            workflow=self._workflow,
            ref=branch_or_tag,
            sha=commit,
        )


async def trigger_prod_deploy(
    *,
    token: str,
    repository: str,
    sha: str,
    workflow: str = "deploy-prod.yml",
    ref: str = "main",
    client: httpx.AsyncClient | None = None,
) -> DeployDispatchResult:
    """Convenience wrapper used by owner-approval handlers."""
    service = DeployTriggerService(
        token=token,
        repository=repository,
        workflow=workflow,
        client=client,
    )
    try:
        return await service.dispatch_prod_deploy(sha=sha, ref=ref)
    finally:
        if client is None:
            await service.close()
