"""Cursor agent model presets exposed in the Telegram UI."""

from __future__ import annotations

from enum import Enum

from beachops.services.cursor_cloud_client import ModelParam, ModelSelection


class CursorModelKey(str, Enum):
    COMPOSER_25 = "composer-2.5"
    FABLE_5 = "fable-5"
    SONNET_5 = "sonnet-5"
    GPT_56_TERRA = "gpt-5.6-terra"


CURSOR_MODEL_LABELS: dict[str, str] = {
    CursorModelKey.COMPOSER_25.value: "Composer 2.5",
    CursorModelKey.FABLE_5.value: "Fable 5",
    CursorModelKey.SONNET_5.value: "Sonnet 5",
    CursorModelKey.GPT_56_TERRA.value: "GPT-5.6 Terra",
}

CURSOR_MODEL_ORDER: tuple[CursorModelKey, ...] = (
    CursorModelKey.COMPOSER_25,
    CursorModelKey.FABLE_5,
    CursorModelKey.SONNET_5,
    CursorModelKey.GPT_56_TERRA,
)


def normalize_cursor_model_key(value: str | None, *, default: str) -> str:
    known = {item.value for item in CursorModelKey}
    if value in known:
        return value  # type: ignore[return-value]
    if value and (
        value.startswith("dyn:")
        or value.startswith("h:")
        or "/" in value
        or "|" in value
    ):
        return value
    if default in known or (
        default
        and (
            default.startswith("dyn:")
            or default.startswith("h:")
            or "/" in default
            or "|" in default
        )
    ):
        return default
    return CursorModelKey.COMPOSER_25.value


def cursor_model_label(key: str) -> str:
    if key in CURSOR_MODEL_LABELS:
        return CURSOR_MODEL_LABELS[key]
    if key.startswith("dyn:"):
        body = key[4:]
        return body.split("|", 1)[0] or key
    if key.startswith("h:"):
        return "Cursor model"
    if "/" in key:
        return key.split("/", 1)[0]
    return key


def resolve_cursor_model(
    key: str,
    *,
    params: dict | None = None,
) -> str | ModelSelection:
    """Map UI key to Cloud Agents API model id or ModelSelection with variants."""
    override_params: tuple[ModelParam, ...] | None = None
    if params:
        override_params = tuple(
            ModelParam(id=str(pid), value=str(pval))
            for pid, pval in params.items()
            if pid is not None and pval is not None
        )

    def _maybe_override(selection: ModelSelection) -> ModelSelection:
        if override_params is None:
            return selection
        return ModelSelection(id=selection.id, params=override_params)

    if key == CursorModelKey.COMPOSER_25.value:
        return _maybe_override(
            ModelSelection(
                id="composer-2.5",
                params=(ModelParam(id="fast", value="true"),),
            )
        )
    if key == CursorModelKey.FABLE_5.value:
        return _maybe_override(
            ModelSelection(
                id="claude-fable-5",
                params=(
                    ModelParam(id="thinking", value="true"),
                    ModelParam(id="context", value="300k"),
                    ModelParam(id="effort", value="high"),
                ),
            )
        )
    if key == CursorModelKey.SONNET_5.value:
        return _maybe_override(
            ModelSelection(
                id="claude-sonnet-5",
                params=(
                    ModelParam(id="thinking", value="true"),
                    ModelParam(id="context", value="300k"),
                    ModelParam(id="effort", value="medium"),
                ),
            )
        )
    if key == CursorModelKey.GPT_56_TERRA.value:
        return _maybe_override(
            ModelSelection(
                id="gpt-5.6-terra",
                params=(
                    ModelParam(id="context", value="272k"),
                    ModelParam(id="reasoning", value="medium"),
                    ModelParam(id="fast", value="false"),
                ),
            )
        )
    if key.startswith("dyn:"):
        # dyn:<model_id>|<param=value,...>
        body = key[4:]
        model_id, _, params_raw = body.partition("|")
        parsed: list[ModelParam] = []
        if params_raw:
            for part in params_raw.split(","):
                pid, _, pval = part.partition("=")
                if pid and pval:
                    parsed.append(ModelParam(id=pid, value=pval))
        return _maybe_override(ModelSelection(id=model_id, params=tuple(parsed)))
    if override_params is not None:
        return ModelSelection(id=key, params=override_params)
    return key
