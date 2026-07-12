"""Dynamic Cursor model catalog with Redis cache and Telegram fingerprints."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from beachops.app_context import AppContext
from beachops.domain.cursor_models import (
    CURSOR_MODEL_ORDER,
    cursor_model_label,
    resolve_cursor_model,
)
from beachops.domain.cursor_tokens import normalize_cursor_token_key
from beachops.services.cursor_cloud_client import (
    CursorCloudError,
    ModelParam,
    ModelSelection,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 3600
_FP_TTL_SEC = 86400


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    display_name: str
    params: tuple[ModelParam, ...] = ()
    ui_key: str = ""
    fingerprint: str = ""


def selection_fingerprint(selection: ModelSelection | str) -> str:
    if isinstance(selection, str):
        raw = selection
    else:
        parts = [selection.id]
        for param in selection.params:
            parts.append(f"{param.id}={param.value}")
        raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def selection_to_ui_key(selection: ModelSelection | str) -> str:
    if isinstance(selection, str):
        return selection if "/" not in selection else f"dyn:{selection}"
    if not selection.params:
        return f"dyn:{selection.id}|"
    encoded = ",".join(f"{p.id}={p.value}" for p in selection.params)
    return f"dyn:{selection.id}|{encoded}"


def validate_ui_models(api_key: str) -> None:
    """Log warnings when a UI preset is missing from the account catalog."""
    import asyncio

    async def _run() -> None:
        from beachops.services.cursor_cloud_client import CursorCloudClient

        try:
            async with CursorCloudClient(api_key=api_key) as client:
                models = await client.list_models()
        except Exception:
            logger.warning("Could not load Cursor model catalog at startup", exc_info=True)
            return
        catalog_ids = {
            str(item.get("id") or item.get("modelId") or "")
            for item in models
            if isinstance(item, dict)
        }
        catalog_ids.discard("")
        for choice in CURSOR_MODEL_ORDER:
            resolved = resolve_cursor_model(choice.value)
            model_id = resolved if isinstance(resolved, str) else resolved.id
            if catalog_ids and model_id not in catalog_ids:
                logger.warning(
                    "UI model preset %s (%s) is not in Cursor catalog for this account",
                    choice.value,
                    model_id,
                )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run())
    else:
        # Bot startup already has a loop; fire-and-forget.
        asyncio.create_task(_run())


async def resolve_user_model_selection(
    app: AppContext,
    user_id: int,
) -> tuple[str, str | ModelSelection]:
    """Resolve stored UI key (+ fingerprint) into API model selection."""
    default = app.settings.cursor_model
    model_key = await app.users.get_cursor_model_key(user_id, default=default)
    params = await app.users.get_cursor_model_params(user_id)
    if model_key.startswith("h:"):
        token_key = await app.users.get_cursor_token_key(user_id)
        resolved = await CursorModelCatalog(app).resolve_fingerprint(
            token_key, model_key[2:]
        )
        if resolved:
            model_key = resolved
        else:
            logger.warning(
                "Unknown model fingerprint for user %s; falling back to %s",
                user_id,
                default,
            )
            model_key = default
    return model_key, resolve_cursor_model(
        model_key, params=params or None
    )


def _cache_key(token_key: str) -> str:
    return f"beachops:cursor:models:{normalize_cursor_token_key(token_key)}"


def _fp_key(token_key: str, fingerprint: str) -> str:
    return (
        f"beachops:cursor:model-fp:"
        f"{normalize_cursor_token_key(token_key)}:{fingerprint}"
    )


def _parse_catalog_item(item: dict[str, Any]) -> CatalogModel | None:
    model_id = str(item.get("id") or item.get("modelId") or "").strip()
    if not model_id:
        return None
    display = str(
        item.get("displayName")
        or item.get("name")
        or item.get("label")
        or model_id
    )
    params: list[ModelParam] = []
    raw_params = item.get("params") or item.get("parameters") or []
    if isinstance(raw_params, list):
        for raw in raw_params:
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or raw.get("name") or "").strip()
            # Prefer explicit default / first enum value when present.
            value = raw.get("value") or raw.get("default")
            if value is None:
                options = raw.get("values") or raw.get("enum") or []
                if isinstance(options, list) and options:
                    value = options[0]
            if pid and value is not None:
                params.append(ModelParam(id=pid, value=str(value)))
    selection = ModelSelection(id=model_id, params=tuple(params))
    ui_key = selection_to_ui_key(selection)
    return CatalogModel(
        id=model_id,
        display_name=display,
        params=tuple(params),
        ui_key=ui_key,
        fingerprint=selection_fingerprint(selection),
    )


class CursorModelCatalog:
    def __init__(self, app: AppContext) -> None:
        self._app = app

    async def list_for_token(
        self,
        token_key: str,
        *,
        force_refresh: bool = False,
    ) -> list[CatalogModel]:
        key = _cache_key(token_key)
        if not force_refresh:
            cached = await self._app.redis.get(key)
            if cached:
                try:
                    payload = json.loads(cached)
                    return [
                        CatalogModel(
                            id=item["id"],
                            display_name=item["display_name"],
                            params=tuple(
                                ModelParam(id=p["id"], value=p["value"])
                                for p in item.get("params") or []
                            ),
                            ui_key=item["ui_key"],
                            fingerprint=item["fingerprint"],
                        )
                        for item in payload
                    ]
                except Exception:
                    logger.warning("Corrupt model cache for %s", token_key, exc_info=True)

        api_key = self._app.settings.cursor_api_key_for(token_key)
        try:
            async with self._app.cursor._client(api_key) as client:
                raw = await client.list_models()
        except CursorCloudError:
            logger.warning("list_models failed for %s", token_key, exc_info=True)
            return self._preset_fallback()

        models = [m for m in (_parse_catalog_item(item) for item in raw) if m]
        if not models:
            models = self._preset_fallback()

        encoded = json.dumps(
            [
                {
                    "id": m.id,
                    "display_name": m.display_name,
                    "params": [{"id": p.id, "value": p.value} for p in m.params],
                    "ui_key": m.ui_key,
                    "fingerprint": m.fingerprint,
                }
                for m in models
            ],
            separators=(",", ":"),
        )
        await self._app.redis.set(key, encoded, ex=_CACHE_TTL_SEC)
        for model in models:
            await self._app.redis.set(
                _fp_key(token_key, model.fingerprint),
                model.ui_key,
                ex=_FP_TTL_SEC,
            )
        return models

    async def resolve_fingerprint(
        self, token_key: str, fingerprint: str
    ) -> str | None:
        value = await self._app.redis.get(_fp_key(token_key, fingerprint))
        if value:
            return value.decode() if isinstance(value, bytes) else str(value)
        models = await self.list_for_token(token_key)
        for model in models:
            if model.fingerprint == fingerprint:
                return model.ui_key
        return None

    def _preset_fallback(self) -> list[CatalogModel]:
        out: list[CatalogModel] = []
        for choice in CURSOR_MODEL_ORDER:
            resolved = resolve_cursor_model(choice.value)
            if isinstance(resolved, str):
                selection = ModelSelection(id=resolved)
            else:
                selection = resolved
            out.append(
                CatalogModel(
                    id=selection.id,
                    display_name=cursor_model_label(choice.value),
                    params=selection.params,
                    ui_key=choice.value,
                    fingerprint=selection_fingerprint(selection),
                )
            )
        return out

    async def options_for_ui(
        self,
        token_key: str,
        *,
        include_dynamic: bool = True,
        dynamic_limit: int = 24,
    ) -> list[dict[str, str]]:
        """Presets first, then dynamic catalog entries."""
        options: list[dict[str, str]] = [
            {"key": choice.value, "label": cursor_model_label(choice.value)}
            for choice in CURSOR_MODEL_ORDER
        ]
        if not include_dynamic:
            return options
        seen = {item["key"] for item in options}
        preset_ids: set[str] = set()
        for choice in CURSOR_MODEL_ORDER:
            resolved = resolve_cursor_model(choice.value)
            preset_ids.add(resolved if isinstance(resolved, str) else resolved.id)
        models = await self.list_for_token(token_key)
        added = 0
        for model in models:
            if model.id in preset_ids:
                continue
            key = f"h:{model.fingerprint}"
            if key in seen or model.ui_key in seen:
                continue
            options.append({"key": key, "label": model.display_name})
            seen.add(key)
            added += 1
            if added >= dynamic_limit:
                break
        return options
