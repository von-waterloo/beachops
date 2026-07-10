"""Helper for the mt/mt2 token switch in the Telegram UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from beachops.domain.cursor_tokens import CursorTokenKey

if TYPE_CHECKING:
    from beachops.app_context import AppContext


async def current_token_key_for_ui(app: AppContext, user_id: int) -> str | None:
    """Token key for keyboards/status, or None when the switch is hidden.

    The switch is shown only when the second token (mt2) is configured.
    """
    if not app.settings.has_cursor_token(CursorTokenKey.MT2.value):
        return None
    return await app.users.get_cursor_token_key(user_id)
