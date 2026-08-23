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
_CACHE_VERSION = 2


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    display_name: str
    params: tuple[ModelParam, ...] = ()
    ui_key: str = ""
    fingerprint: str = ""
    aliases: tuple[str, ...] = ()
    variants: tuple[tuple[ModelParam, ...], ...] = ()


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
        parsed = [m for m in (parse_catalog_item(item) for item in models) if m]
        for choice in CURSOR_MODEL_ORDER:
            resolved = resolve_cursor_model(choice.value)
            snapped = apply_catalog_variant(resolved, parsed)
            model_id = snapped if isinstance(snapped, str) else snapped.id
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
    token_key = await app.users.get_cursor_token_key(user_id)
    if model_key.startswith("h:"):
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
    selection = resolve_cursor_model(model_key, params=params or None)
    catalog = await CursorModelCatalog(app).list_for_token(token_key)
    return model_key, apply_catalog_variant(selection, catalog)


def _cache_key(token_key: str) -> str:
    return f"beachops:cursor:models:{normalize_cursor_token_key(token_key)}"


def _fp_key(token_key: str, fingerprint: str) -> str:
    return (
        f"beachops:cursor:model-fp:"
        f"{normalize_cursor_token_key(token_key)}:{fingerprint}"
    )


def _params_to_cache(params: tuple[ModelParam, ...]) -> list[dict[str, str]]:
    return [{"id": param.id, "value": param.value} for param in params]


def _params_from_cache(raw: Any) -> tuple[ModelParam, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        ModelParam(id=str(item["id"]), value=str(item["value"]))
        for item in raw
        if isinstance(item, dict) and item.get("id") is not None
    )


def _catalog_to_cache(model: CatalogModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "display_name": model.display_name,
        "params": _params_to_cache(model.params),
        "ui_key": model.ui_key,
        "fingerprint": model.fingerprint,
        "aliases": list(model.aliases),
        "variants": [_params_to_cache(variant) for variant in model.variants],
    }


def _catalog_from_cache(item: dict[str, Any]) -> CatalogModel:
    variants = tuple(_params_from_cache(variant) for variant in item.get("variants") or [])
    params = _params_from_cache(item.get("params") or [])
    aliases = tuple(str(alias) for alias in item.get("aliases") or [])
    return CatalogModel(
        id=item["id"],
        display_name=item["display_name"],
        params=params,
        ui_key=item["ui_key"],
        fingerprint=item["fingerprint"],
        aliases=aliases,
        variants=variants,
    )


def _models_from_cache(payload: Any) -> list[CatalogModel] | None:
    if not isinstance(payload, dict) or payload.get("v") != _CACHE_VERSION:
        return None
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        return None
    return [_catalog_from_cache(item) for item in raw_models if isinstance(item, dict)]


def _scalar_param_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        inner = value.get("value")
        if inner is None:
            return None
        return str(inner)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _params_from_raw(raw_params: Any) -> tuple[ModelParam, ...]:
    if not isinstance(raw_params, list):
        return ()
    out: list[ModelParam] = []
    for raw in raw_params:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or raw.get("name") or "").strip()
        value = _scalar_param_value(raw.get("value"))
        if value is None:
            value = _scalar_param_value(raw.get("default"))
        if value is None:
            options = raw.get("values") or raw.get("enum") or []
            if isinstance(options, list) and options:
                value = _scalar_param_value(options[0])
        if pid and value is not None:
            out.append(ModelParam(id=pid, value=value))
    return tuple(out)


def _variant_params(variant: Any) -> tuple[ModelParam, ...]:
    if not isinstance(variant, dict):
        return ()
    return _params_from_raw(variant.get("params") or [])


def _all_variants(item: dict[str, Any]) -> tuple[tuple[ModelParam, ...], ...]:
    raw = item.get("variants") or []
    if not isinstance(raw, list):
        return ()
    return tuple(_variant_params(variant) for variant in raw if isinstance(variant, dict))


def _default_params(item: dict[str, Any]) -> tuple[ModelParam, ...]:
    raw = item.get("variants") or []
    if isinstance(raw, list) and raw:
        default = next(
            (variant for variant in raw if isinstance(variant, dict) and variant.get("isDefault")),
            None,
        )
        chosen = default if isinstance(default, dict) else (
            raw[0] if isinstance(raw[0], dict) else None
        )
        if chosen is not None:
            return _variant_params(chosen)
    return _params_from_raw(item.get("params") or item.get("parameters") or [])


def parse_catalog_item(item: dict[str, Any]) -> CatalogModel | None:
    """Parse one GET /v1/models item, preferring the default variant params."""
    model_id = str(item.get("id") or item.get("modelId") or "").strip()
    if not model_id:
        return None
    display = str(
        item.get("displayName")
        or item.get("name")
        or item.get("label")
        or model_id
    )
    aliases_raw = item.get("aliases") or []
    aliases = (
        tuple(str(alias) for alias in aliases_raw if alias)
        if isinstance(aliases_raw, list)
        else ()
    )
    params = _default_params(item)
    variants = _all_variants(item)
    if not variants and params:
        variants = (params,)
    selection = ModelSelection(id=model_id, params=params)
    return CatalogModel(
        id=model_id,
        display_name=display,
        params=params,
        ui_key=selection_to_ui_key(selection),
        fingerprint=selection_fingerprint(selection),
        aliases=aliases,
        variants=variants,
    )


def _parse_catalog_item(item: dict[str, Any]) -> CatalogModel | None:
    return parse_catalog_item(item)


def _param_map(params: tuple[ModelParam, ...]) -> dict[str, str]:
    return {param.id: param.value for param in params}


def _variants_of(catalog: CatalogModel) -> tuple[tuple[ModelParam, ...], ...]:
    if catalog.variants:
        return catalog.variants
    if catalog.params:
        return (catalog.params,)
    return ()


def coerce_selection_to_variant(
    selection: ModelSelection | str,
    catalog: CatalogModel | None,
) -> ModelSelection | str:
    """Snap a selection to a concrete catalog variant (exact id+params)."""
    if catalog is None:
        return selection
    current = {} if isinstance(selection, str) else _param_map(selection.params)
    variants = _variants_of(catalog)
    if not variants:
        return selection

    catalog_default = _param_map(catalog.params)
    default = variants[0]
    for variant in variants:
        if _param_map(variant) == catalog_default:
            default = variant
            break

    for variant in variants:
        if _param_map(variant) == current:
            return ModelSelection(id=catalog.id, params=variant)

    if not current:
        return ModelSelection(id=catalog.id, params=default)

    matches = [
        variant
        for variant in variants
        if current.items() <= _param_map(variant).items()
    ]
    if len(matches) == 1:
        return ModelSelection(id=catalog.id, params=matches[0])
    if len(matches) > 1:
        for variant in matches:
            if _param_map(variant) == catalog_default:
                return ModelSelection(id=catalog.id, params=variant)
        return ModelSelection(id=catalog.id, params=matches[0])
    return ModelSelection(id=catalog.id, params=default)


def apply_catalog_variant(
    selection: ModelSelection | str,
    models: list[CatalogModel],
) -> ModelSelection | str:
    model_id = selection if isinstance(selection, str) else selection.id
    match = next(
        (item for item in models if item.id == model_id or model_id in item.aliases),
        None,
    )
    return coerce_selection_to_variant(selection, match)


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
                    models = _models_from_cache(json.loads(cached))
                    if models is not None:
                        return models
                except Exception:
                    logger.warning("Corrupt model cache for %s", token_key, exc_info=True)

        api_key = self._app.settings.cursor_api_key_for(token_key)
        try:
            async with self._app.cursor._client(api_key) as client:
                raw = await client.list_models()
        except CursorCloudError:
            logger.warning("list_models failed for %s", token_key, exc_info=True)
            return self._preset_fallback()

        models = [m for m in (parse_catalog_item(item) for item in raw) if m]
        if not models:
            models = self._preset_fallback()

        encoded = json.dumps(
            {
                "v": _CACHE_VERSION,
                "models": [_catalog_to_cache(model) for model in models],
            },
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
                    variants=(selection.params,) if selection.params else (),
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
