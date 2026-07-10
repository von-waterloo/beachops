"""Stream UX: thinking visibility and run phase labels."""

from __future__ import annotations

from typing import Literal

from beachops.domain.models import UserMode

StreamThinkingMode = Literal["off", "preview", "admin"]
ThinkingDisplay = Literal["none", "count", "preview"]


def resolve_thinking_display(
    stream_thinking: StreamThinkingMode,
    mode: UserMode,
    *,
    is_admin: bool,
) -> ThinkingDisplay:
    if stream_thinking == "off":
        return "none"
    if stream_thinking == "admin" and not is_admin:
        return "count" if mode == UserMode.ASK else "none"
    if mode == UserMode.ASK:
        return "count"
    return "preview"
