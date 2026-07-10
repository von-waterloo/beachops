"""Unit tests for GitHub Actions deploy_trigger helper."""

from __future__ import annotations

import json

import httpx
import pytest

from beachops.services.deploy_trigger import (
    DeployTriggerError,
    DeployTriggerService,
    trigger_prod_deploy,
)


@pytest.mark.asyncio
async def test_dispatch_prod_deploy_posts_workflow_dispatch() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST"
        assert (
            request.url.path
            == "/repos/stekirill/beachops/actions/workflows/deploy-prod.yml/dispatches"
        )
        payload = json.loads(request.content.decode())
        assert payload == {"ref": "main", "inputs": {"sha": "abc1234deadbeef"}}
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.github.com",
    ) as client:
        result = await trigger_prod_deploy(
            token="ghp_test",
            repository="stekirill/beachops",
            sha="abc1234deadbeef",
            ref="main",
            client=client,
        )

    assert result.repository == "stekirill/beachops"
    assert result.workflow == "deploy-prod.yml"
    assert result.sha == "abc1234deadbeef"
    assert result.ref == "main"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_dispatch_rejects_short_sha() -> None:
    service = DeployTriggerService(
        token="ghp_test",
        repository="stekirill/beachops",
        client=httpx.AsyncClient(),
    )
    try:
        with pytest.raises(DeployTriggerError, match="sha"):
            await service.dispatch_prod_deploy(sha="abc")
    finally:
        await service.close()


def test_missing_token_raises() -> None:
    with pytest.raises(DeployTriggerError, match="GITHUB_TOKEN"):
        DeployTriggerService(token="  ", repository="stekirill/beachops")
