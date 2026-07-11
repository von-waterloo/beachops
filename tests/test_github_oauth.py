"""GitHub OAuth helpers (no live GitHub)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from beachops.web.github_oauth import (
    GithubOAuthNotConfigured,
    begin_oauth,
    callback_url,
    github_oauth_configured,
)
from beachops.web.passkey_auth import _bot_id_from_token


def test_bot_id_from_token() -> None:
    assert _bot_id_from_token("123456789:AAHsecret") == 123456789
    assert _bot_id_from_token("bad") is None


def test_github_oauth_configured() -> None:
    assert github_oauth_configured(
        SimpleNamespace(
            github_oauth_client_id="id",
            github_oauth_client_secret="secret",
            webapp_base_url="https://beachops.example.com",
        )
    )
    assert not github_oauth_configured(
        SimpleNamespace(
            github_oauth_client_id="",
            github_oauth_client_secret="secret",
            webapp_base_url="https://beachops.example.com",
        )
    )


def test_callback_url() -> None:
    settings = SimpleNamespace(webapp_base_url="https://beachops.example.com/")
    assert callback_url(settings) == "https://beachops.example.com/api/auth/github/callback"


@pytest.mark.asyncio
async def test_begin_oauth_requires_config() -> None:
    context = SimpleNamespace(
        settings=SimpleNamespace(
            github_oauth_client_id="",
            github_oauth_client_secret="",
            webapp_base_url="",
        )
    )
    with pytest.raises(GithubOAuthNotConfigured):
        await begin_oauth(context, user_id=1)  # type: ignore[arg-type]
