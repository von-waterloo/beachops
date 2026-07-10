"""Read-only GitHub PR metadata adapter used by BeachOps review screens."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class GitHubReviewError(ValueError):
    pass


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    additions: int
    deletions: int
    patch: str | None
    sensitive: bool = False


_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".ppk"}


def _is_sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    return (
        name in _SENSITIVE_NAMES
        or any(name.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)
        or "/.ssh/" in f"/{normalized}"
    )


def parse_github_pr_url(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise GitHubReviewError("unsupported pull request URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "pull":
        raise GitHubReviewError("invalid pull request URL")
    try:
        number = int(parts[3])
    except ValueError as exc:
        raise GitHubReviewError("invalid pull request number") from exc
    if number <= 0:
        raise GitHubReviewError("invalid pull request number")
    return parts[0], parts[1], number


class GitHubReviewService:
    def __init__(
        self,
        *,
        token: str,
        redact,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._redact = redact
        self._client = client or httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_changed_files(
        self,
        *,
        pr_url: str,
        expected_repo_url: str,
    ) -> list[ChangedFile]:
        owner, repo, number = parse_github_pr_url(pr_url)
        expected = f"https://github.com/{owner}/{repo}".lower()
        if expected_repo_url.removesuffix(".git").rstrip("/").lower() != expected:
            raise GitHubReviewError("pull request is outside the allowed repository")

        response = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{number}/files",
            params={"per_page": 100},
        )
        response.raise_for_status()
        files: list[ChangedFile] = []
        for raw in response.json():
            path = str(raw.get("filename", ""))
            sensitive = _is_sensitive_path(path)
            patch = None if sensitive else raw.get("patch")
            files.append(
                ChangedFile(
                    path=path,
                    status=str(raw.get("status", "modified")),
                    additions=int(raw.get("additions", 0)),
                    deletions=int(raw.get("deletions", 0)),
                    patch=self._redact(str(patch)) if patch else None,
                    sensitive=sensitive,
                )
            )
        return files
