"""Startup validation of UI model presets against Cursor catalog."""

from __future__ import annotations

import logging

from cursor_sdk import Cursor, ModelSelection

from beachops.domain.cursor_models import CURSOR_MODEL_ORDER, resolve_cursor_model

logger = logging.getLogger(__name__)


def validate_ui_models(api_key: str) -> None:
    """Log warnings when a UI preset is missing from the account catalog."""
    try:
        models = Cursor.models.list(api_key=api_key)
    except Exception:
        logger.warning("Could not load Cursor model catalog at startup", exc_info=True)
        return

    catalog_ids = {model.id for model in models}
    for choice in CURSOR_MODEL_ORDER:
        resolved = resolve_cursor_model(choice.value)
        model_id = resolved if isinstance(resolved, str) else resolved.id
        if model_id not in catalog_ids:
            logger.warning(
                "UI model preset %s (%s) is not in Cursor catalog for this account",
                choice.value,
                model_id,
            )
