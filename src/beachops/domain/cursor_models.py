"""Cursor agent model presets exposed in the Telegram UI."""

from __future__ import annotations

from enum import Enum

from beachops.services.cursor_cloud_client import ModelParam, ModelSelection


class CursorModelKey(str, Enum):
    GROK_47 = "grok-4.7"
    GEMINI_4 = "gemini-4"
    OPUS_55 = "opus-5.5"
    SONNET_55 = "sonnet-5.5"


CURSOR_MODEL_LABELS: dict[str, str] = {
    CursorModelKey.GROK_47.value: "Grok 4.7",
    CursorModelKey.GEMINI_4.value: "Gemini 4",
    CursorModelKey.OPUS_55.value: "Opus 5.5",
    CursorModelKey.SONNET_55.value: "Sonnet 5.5",
}

CURSOR_MODEL_ORDER: tuple[CursorModelKey, ...] = (
    CursorModelKey.GROK_47,
    CursorModelKey.GEMINI_4,
    CursorModelKey.OPUS_55,
    CursorModelKey.SONNET_55,
)

# Legacy UI keys remapped after catalog swaps (read path before DB migration).
_LEGACY_CURSOR_MODEL_KEYS: dict[str, str] = {
    "composer-2.5": CursorModelKey.GROK_47.value,
    "grok-4.6": CursorModelKey.GROK_47.value,
    "fable-5": CursorModelKey.GEMINI_4.value,
    "opus-5": CursorModelKey.OPUS_55.value,
    "sonnet-5": CursorModelKey.SONNET_55.value,
    "gpt-5.6-terra": CursorModelKey.SONNET_55.value,
}


def normalize_cursor_model_key(value: str | None, *, default: str) -> str:
    known = {item.value for item in CursorModelKey}
    if value in _LEGACY_CURSOR_MODEL_KEYS:
        return _LEGACY_CURSOR_MODEL_KEYS[value]
    if value in known:
        return value  # type: ignore[return-value]
    if value and (
        value.startswith("dyn:")
        or value.startswith("h:")
        or "/" in value
        or "|" in value
    ):
        return value
    if default in _LEGACY_CURSOR_MODEL_KEYS:
        return _LEGACY_CURSOR_MODEL_KEYS[default]
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
    return CursorModelKey.GROK_47.value


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

    if key == CursorModelKey.GROK_47.value:
        return _maybe_override(
            ModelSelection(
                id="grok-4.7",
                params=(
                    ModelParam(id="context", value="256k"),
                    ModelParam(id="reasoning_effort", value="xhigh"),
                    ModelParam(id="fast", value="false"),
                ),
            )
        )
    if key == CursorModelKey.GEMINI_4.value:
        return _maybe_override(
            ModelSelection(
                id="gemini-4-argon",
                params=(ModelParam(id="reasoning_effort", value="high"),),
            )
        )
    if key == CursorModelKey.OPUS_55.value:
        return _maybe_override(
            ModelSelection(
                id="claude-opus-5-5",
                params=(
                    ModelParam(id="context", value="300k"),
                    ModelParam(id="effort", value="high"),
                    ModelParam(id="fast", value="false"),
                ),
            )
        )
    if key == CursorModelKey.SONNET_55.value:
        return _maybe_override(
            ModelSelection(
                id="claude-sonnet-5-5",
                params=(
                    ModelParam(id="context", value="1m"),
                    ModelParam(id="reasoning_effort", value="high"),
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
