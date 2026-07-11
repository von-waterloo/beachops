"""GitHub OAuth for listing and pinning user repositories."""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from beachops.app_context import AppContext
from beachops.services.payload_crypto import PayloadCryptoError

logger = logging.getLogger(__name__)

_STATE_PREFIX = "beachops:github-oauth:"
_AAD = b"beachops:github_oauth:v1"
_SCOPES = "repo read:user"


class GithubOAuthError(Exception):
    pass


class GithubOAuthNotConfigured(GithubOAuthError):
    pass


class GithubOAuthNotConnected(GithubOAuthError):
    pass


def github_oauth_configured(settings) -> bool:
    return bool(
        settings.github_oauth_client_id.strip()
        and settings.github_oauth_client_secret.strip()
        and settings.webapp_base_url.strip()
    )


def callback_url(settings) -> str:
    base = settings.webapp_base_url.rstrip("/")
    return f"{base}/api/auth/github/callback"


async def begin_oauth(context: AppContext, *, user_id: int) -> str:
    if not github_oauth_configured(context.settings):
        raise GithubOAuthNotConfigured("GitHub OAuth is not configured")
    state = secrets.token_urlsafe(24)
    await context.redis.set(
        f"{_STATE_PREFIX}{state}",
        str(user_id).encode("utf-8"),
        ex=600,
    )
    params = {
        "client_id": context.settings.github_oauth_client_id.strip(),
        "redirect_uri": callback_url(context.settings),
        "scope": _SCOPES,
        "state": state,
        "allow_signup": "false",
    }
    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"


async def complete_oauth(
    context: AppContext,
    *,
    code: str,
    state: str,
) -> int:
    """Exchange code for token; return tg_user_id from state."""
    if not github_oauth_configured(context.settings):
        raise GithubOAuthNotConfigured("GitHub OAuth is not configured")
    if not code or not state or len(state) > 128:
        raise GithubOAuthError("invalid OAuth state")
    raw = await context.redis.getdel(f"{_STATE_PREFIX}{state}")
    if not raw:
        raise GithubOAuthError("OAuth state expired — start again from BeachOps")
    try:
        user_id = int(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GithubOAuthError("invalid OAuth state") from exc

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": context.settings.github_oauth_client_id.strip(),
                "client_secret": context.settings.github_oauth_client_secret.strip(),
                "code": code,
                "redirect_uri": callback_url(context.settings),
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise GithubOAuthError(
                str(token_payload.get("error_description") or "GitHub denied access")
            )
        scopes = str(token_payload.get("scope") or _SCOPES)
        user_response = await client.get(
            "https://api.github.com/user",
            headers=_api_headers(access_token),
        )
        user_response.raise_for_status()
        login = str(user_response.json().get("login") or "") or None

    try:
        encrypted = context.payload_crypto.encrypt(
            access_token.encode("utf-8"),
            aad=_AAD,
        )
    except PayloadCryptoError as exc:
        raise GithubOAuthError("failed to store GitHub token") from exc

    await context.github_tokens.upsert(
        user_id,
        access_token_enc=encrypted,
        github_login=login,
        scopes=scopes,
    )
    return user_id


async def disconnect(context: AppContext, *, user_id: int) -> None:
    await context.github_tokens.delete(user_id)


async def connection_status(context: AppContext, *, user_id: int) -> dict[str, Any]:
    row = await context.github_tokens.get(user_id)
    return {
        "configured": github_oauth_configured(context.settings),
        "connected": row is not None,
        "login": row.github_login if row else None,
    }


async def list_repositories(
    context: AppContext,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    token = await _decrypt_token(context, user_id)
    page = max(1, page)
    per_page = min(100, max(1, per_page))
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers=_api_headers(token),
            params={
                "affiliation": "owner,collaborator,organization_member",
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            },
        )
        if response.status_code == 401:
            await context.github_tokens.delete(user_id)
            raise GithubOAuthNotConnected("GitHub session expired — reconnect")
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        raise GithubOAuthError("unexpected GitHub response")
    repos: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        html_url = str(item.get("html_url") or "").rstrip("/")
        full_name = str(item.get("full_name") or "")
        default_branch = str(item.get("default_branch") or "dev")
        if not html_url.startswith("https://github.com/"):
            continue
        repos.append(
            {
                "url": html_url,
                "fullName": full_name,
                "private": bool(item.get("private")),
                "defaultBranch": default_branch,
            }
        )
    return repos


async def _decrypt_token(context: AppContext, user_id: int) -> str:
    row = await context.github_tokens.get(user_id)
    if row is None:
        raise GithubOAuthNotConnected("Connect GitHub first")
    try:
        return context.payload_crypto.decrypt(
            row.access_token_enc,
            aad=_AAD,
        ).decode("utf-8")
    except PayloadCryptoError as exc:
        await context.github_tokens.delete(user_id)
        raise GithubOAuthNotConnected("GitHub token invalid — reconnect") from exc


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "beachops",
    }
