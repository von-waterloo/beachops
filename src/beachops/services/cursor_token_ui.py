"""Helper for the mt/mt2/mt3 token switch in the Telegram UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from beachops.config.settings import Settings
from beachops.domain.cursor_tokens import CURSOR_TOKEN_ORDER, CursorTokenKey

if TYPE_CHECKING:
    from beachops.app_context import AppContext


def configured_cursor_token_keys(settings: Settings) -> tuple[str, ...]:
    """Keys that have a non-empty API key on the server."""
    return tuple(
        choice.value
        for choice in CURSOR_TOKEN_ORDER
        if settings.has_cursor_token(choice.value)
    )


def available_token_keys_for_ui(settings: Settings) -> tuple[str, ...] | None:
    """Configured keys for the switch row, or None when the row should be hidden.

    The switch is shown when at least one extra key (mt2/mt3) is configured;
    only filled keys appear as buttons.
    """
    available = configured_cursor_token_keys(settings)
    if not any(key != CursorTokenKey.MT.value for key in available):
        return None
    return available


async def token_ui_pair(
    app: AppContext, user_id: int
) -> tuple[str | None, tuple[str, ...] | None]:
    """``(current_key, available_keys)`` for keyboards; both None when hidden."""
    available = available_token_keys_for_ui(app.settings)
    if available is None:
        return None, None
    current = await app.users.get_cursor_token_key(user_id)
    if current not in available:
        current = available[0]
    return current, available


async def current_token_key_for_ui(app: AppContext, user_id: int) -> str | None:
    """Token key for keyboards/status, or None when the switch is hidden."""
    current, _available = await token_ui_pair(app, user_id)
    return current
