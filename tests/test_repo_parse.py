"""Tests for /repo add argument parsing."""

from __future__ import annotations

from beachops.services.repo_parse import (
    alias_from_github_url,
    parse_repo_add_args,
    repo_add_usage,
)


def test_alias_from_url():
    assert alias_from_github_url("https://github.com/acme/my-app") == "my-app"
    assert alias_from_github_url("https://github.com/acme/my-app.git") == "my-app"


def test_parse_url_only():
    parsed = parse_repo_add_args(
        ["add", "https://github.com/acme/backend"],
        default_branch="dev",
    )
    assert parsed is not None
    assert parsed.alias == "backend"
    assert parsed.github_url == "https://github.com/acme/backend"
    assert parsed.default_branch == "dev"


def test_parse_url_and_branch():
    parsed = parse_repo_add_args(
        ["add", "https://github.com/acme/backend", "main"],
        default_branch="dev",
    )
    assert parsed is not None
    assert parsed.default_branch == "main"


def test_parse_legacy_alias_url():
    parsed = parse_repo_add_args(
        ["add", "api", "https://github.com/acme/backend"],
        default_branch="dev",
    )
    assert parsed is not None
    assert parsed.alias == "api"
    assert parsed.github_url == "https://github.com/acme/backend"


def test_parse_invalid():
    assert parse_repo_add_args(["add"], default_branch="dev") is None
    assert parse_repo_add_args(["add", "only-alias"], default_branch="dev") is None


def test_usage_non_empty():
    assert "github.com" in repo_add_usage()
