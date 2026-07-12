"""Cursor account / repository health diagnostics with rate limits."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from beachops.app_context import AppContext
from beachops.domain.cursor_tokens import normalize_cursor_token_key
from beachops.services.cursor_cloud_client import CursorCloudError
from beachops.services.cursor_token_ui import configured_cursor_token_keys

logger = logging.getLogger(__name__)

_ME_TTL_SEC = 3600
_REPOS_TTL_SEC = 300
_REPOS_MIN_INTERVAL_SEC = 300


@dataclass(frozen=True, slots=True)
class TokenHealth:
    token_key: str
    ok: bool
    identity: str | None = None
    error: str | None = None
    repository_count: int | None = None
    has_active_repo: bool | None = None


class CursorHealthService:
    def __init__(self, app: AppContext) -> None:
        self._app = app

    def _me_key(self, token_key: str) -> str:
        return f"beachops:cursor:me:{normalize_cursor_token_key(token_key)}"

    def _repos_key(self, token_key: str) -> str:
        return f"beachops:cursor:repos:{normalize_cursor_token_key(token_key)}"

    def _repos_lock_key(self, token_key: str) -> str:
        return f"beachops:cursor:repos:lock:{normalize_cursor_token_key(token_key)}"

    async def get_me(
        self,
        token_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        key = self._me_key(token_key)
        if not force_refresh:
            cached = await self._app.redis.get(key)
            if cached:
                try:
                    return json.loads(cached)
                except Exception:
                    pass
        api_key = self._app.settings.cursor_api_key_for(token_key)
        async with self._app.cursor._client(api_key) as client:
            payload = await client.me()
        await self._app.redis.set(
            key, json.dumps(payload, separators=(",", ":")), ex=_ME_TTL_SEC
        )
        return payload

    async def list_repositories(
        self,
        token_key: str,
        *,
        force_refresh: bool = False,
    ) -> list[str]:
        key = self._repos_key(token_key)
        if not force_refresh:
            cached = await self._app.redis.get(key)
            if cached:
                try:
                    payload = json.loads(cached)
                    if isinstance(payload, list):
                        return [str(item) for item in payload]
                except Exception:
                    pass

        lock_key = self._repos_lock_key(token_key)
        # Rate limit: at most one live fetch per token every 5 minutes.
        acquired = await self._app.redis.set(
            lock_key, "1", nx=True, ex=_REPOS_MIN_INTERVAL_SEC
        )
        if not acquired and not force_refresh:
            cached = await self._app.redis.get(key)
            if cached:
                try:
                    payload = json.loads(cached)
                    if isinstance(payload, list):
                        return [str(item) for item in payload]
                except Exception:
                    pass
            return []

        if force_refresh:
            await self._app.redis.set(lock_key, "1", ex=_REPOS_MIN_INTERVAL_SEC)

        api_key = self._app.settings.cursor_api_key_for(token_key)
        try:
            async with self._app.cursor._client(api_key) as client:
                urls = await client.list_repositories()
        except CursorCloudError:
            logger.warning("list_repositories failed for %s", token_key, exc_info=True)
            return []

        await self._app.redis.set(
            key, json.dumps(urls, separators=(",", ":")), ex=_REPOS_TTL_SEC
        )
        return urls

    @staticmethod
    def _identity_from_me(payload: dict[str, Any]) -> str | None:
        for field in ("email", "userEmail", "name", "apiKeyName", "id"):
            value = payload.get(field)
            if value:
                return str(value)
        user = payload.get("user")
        if isinstance(user, dict):
            for field in ("email", "name", "id"):
                value = user.get(field)
                if value:
                    return str(value)
        return None

    async def snapshot_for_user(
        self,
        user_id: int,
        *,
        is_owner: bool,
        force_refresh: bool = False,
        active_repo_url: str | None = None,
    ) -> dict[str, Any]:
        token_key = await self._app.users.get_cursor_token_key(user_id)
        keys = (
            configured_cursor_token_keys(self._app.settings)
            if is_owner
            else (token_key,)
        )
        tokens: list[dict[str, Any]] = []
        for key in keys:
            try:
                me = await self.get_me(key, force_refresh=force_refresh)
                identity = self._identity_from_me(me) if is_owner else None
                repos = await self.list_repositories(
                    key, force_refresh=force_refresh and key == token_key
                )
                has_active = None
                if active_repo_url:
                    normalized = active_repo_url.rstrip("/").lower()
                    has_active = any(
                        url.rstrip("/").lower() == normalized for url in repos
                    ) if repos else None
                tokens.append(
                    {
                        "tokenKey": key,
                        "ok": True,
                        "identity": identity,
                        "repositoryCount": len(repos) if repos else None,
                        "hasActiveRepo": has_active if key == token_key else None,
                        "active": key == token_key,
                    }
                )
            except CursorCloudError as exc:
                tokens.append(
                    {
                        "tokenKey": key,
                        "ok": False,
                        "identity": None,
                        "error": f"HTTP {exc.status_code}" if exc.status_code else "error",
                        "active": key == token_key,
                    }
                )
            except Exception:
                logger.warning("health check failed for %s", key, exc_info=True)
                tokens.append(
                    {
                        "tokenKey": key,
                        "ok": False,
                        "error": "unavailable",
                        "active": key == token_key,
                    }
                )
        active = next((item for item in tokens if item.get("active")), None)
        return {
            "ok": bool(active and active.get("ok")),
            "activeTokenKey": token_key,
            "tokens": tokens if is_owner else [
                {
                    "tokenKey": token_key,
                    "ok": bool(active and active.get("ok")),
                    "repositoryCount": active.get("repositoryCount") if active else None,
                    "hasActiveRepo": active.get("hasActiveRepo") if active else None,
                    "active": True,
                }
            ],
        }
