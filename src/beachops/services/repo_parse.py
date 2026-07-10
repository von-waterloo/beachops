"""Parse /repo add arguments (URL-only or legacy alias + URL)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepoAddParams:
    alias: str
    github_url: str
    default_branch: str


# Aliases end up in inline callback_data ("repo:{alias}"), which Telegram caps at
# 64 bytes total — keep well under that so the prefix + id never overflows.
MAX_ALIAS_LEN = 40


_REPO_ADD_USAGE = (
    "Использование:\n"
    "/repo add https://github.com/org/repo\n"
    "/repo add https://github.com/org/repo main\n\n"
    "Ветку можно не указывать — подставится dev (или DEFAULT_BRANCH на сервере)."
)


def repo_add_usage() -> str:
    return _REPO_ADD_USAGE


def is_github_repo_url(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized.startswith("github.com/"):
        return True
    return normalized.startswith("https://github.com/") or normalized.startswith(
        "http://github.com/"
    )


def normalize_github_url(url: str) -> str:
    stripped = url.strip()
    if stripped.lower().startswith("github.com/"):
        return f"https://{stripped}"
    return stripped


def normalize_github_repo_url(url: str) -> str:
    """https://github.com/owner/repo — strips /actions, /tree/branch, etc."""
    normalized = normalize_github_url(url.strip()).rstrip("/")
    if "github.com/" not in normalized.lower():
        return normalized
    path = normalized.split("github.com/", 1)[1]
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"https://github.com/{owner}/{repo}"
    if parts:
        return f"https://github.com/{parts[0]}"
    return normalized


def alias_from_github_url(url: str) -> str:
    normalized = normalize_github_url(url).rstrip("/")
    if "github.com/" not in normalized.lower():
        return "repo"
    path = normalized.split("github.com/", 1)[1]
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        name = parts[1]
    elif parts:
        name = parts[0]
    else:
        return "repo"
    if name.endswith(".git"):
        name = name[:-4]
    return (name or "repo")[:MAX_ALIAS_LEN]


def parse_repo_add_args(
    args: list[str],
    *,
    default_branch: str,
) -> RepoAddParams | None:
    """Parse tokens after /repo add. Returns None if arguments are invalid."""
    if not args or args[0] != "add":
        return None

    rest = args[1:]
    if not rest:
        return None

    branch_default = default_branch.strip() or "dev"

    if is_github_repo_url(rest[0]):
        url = normalize_github_url(rest[0])
        branch = rest[1].strip() if len(rest) > 1 else branch_default
        return RepoAddParams(
            alias=alias_from_github_url(url),
            github_url=url,
            default_branch=branch,
        )

    if len(rest) >= 2 and is_github_repo_url(rest[1]):
        url = normalize_github_url(rest[1])
        branch = rest[2].strip() if len(rest) > 2 else branch_default
        return RepoAddParams(
            alias=rest[0].strip(),
            github_url=url,
            default_branch=branch,
        )

    return None
