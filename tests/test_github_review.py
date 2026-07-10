from __future__ import annotations

import httpx
import pytest

from beachops.services.github_review import (
    GitHubReviewError,
    GitHubReviewService,
    parse_github_pr_url,
)


def test_parse_github_pr_url_is_strict() -> None:
    assert parse_github_pr_url("https://github.com/acme/app/pull/12") == (
        "acme",
        "app",
        12,
    )
    with pytest.raises(GitHubReviewError):
        parse_github_pr_url("https://example.com/acme/app/pull/12")


async def test_review_redacts_patch_and_hides_sensitive_files() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/app/pulls/12/files"
        return httpx.Response(
            200,
            json=[
                {
                    "filename": "src/app.py",
                    "status": "modified",
                    "additions": 2,
                    "deletions": 1,
                    "patch": "+token=secret",
                },
                {
                    "filename": ".env.production",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "patch": "+API_KEY=secret",
                },
            ],
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )
    service = GitHubReviewService(
        token="not-used",
        redact=lambda value: value.replace("secret", "[REDACTED]"),
        client=client,
    )
    files = await service.list_changed_files(
        pr_url="https://github.com/acme/app/pull/12",
        expected_repo_url="https://github.com/acme/app.git",
    )
    assert files[0].patch == "+token=[REDACTED]"
    assert files[1].sensitive is True
    assert files[1].patch is None
    await client.aclose()


async def test_review_rejects_repo_mismatch() -> None:
    client = httpx.AsyncClient()
    service = GitHubReviewService(
        token="not-used",
        redact=lambda value: value,
        client=client,
    )
    with pytest.raises(GitHubReviewError, match="outside"):
        await service.list_changed_files(
            pr_url="https://github.com/acme/app/pull/12",
            expected_repo_url="https://github.com/other/app",
        )
    await client.aclose()
