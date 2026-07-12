"""Aggregate Cursor run stream into renderable state."""

from __future__ import annotations

from dataclasses import dataclass, field

from beachops.services.stream_display import ThinkingDisplay
from beachops.services.redaction import redact_text
from beachops.services.ui_copy import (
    EMPTY_STREAM_HINT,
    format_thinking_line,
    format_thinking_preview,
    format_tool_line,
    tool_display_name,
)


@dataclass
class StreamState:
    assistant_text: str = ""
    thinking_chars: int = 0
    thinking_text: str = ""
    tool_lines: list[str] = field(default_factory=list)
    status: str = "running"
    run_id: str | None = None
    agent_id: str | None = None
    pr_url: str | None = None
    final_text: str | None = None
    duration_ms: int | None = None
    branch_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    plan_text: str | None = None
    plan_name: str | None = None
    plan_tool_called: bool = False
    last_event_id: str | None = None

    def set_plan(self, text: str, *, name: str | None = None) -> None:
        self.plan_text = redact_text(text).strip() or None
        if name:
            self.plan_name = name

    def append_assistant(self, chunk: str) -> None:
        self.assistant_text = redact_text(self.assistant_text + chunk)

    def append_thinking(self, chunk: str) -> None:
        self.thinking_chars += len(chunk)
        if chunk:
            self.thinking_text = redact_text(self.thinking_text + chunk)
            if len(self.thinking_text) > 4000:
                self.thinking_text = self.thinking_text[-4000:]

    def upsert_tool(self, name: str, status: str) -> None:
        label = format_tool_line(name, status)
        needle = f" {tool_display_name(name)} — "
        if self.tool_lines and needle in self.tool_lines[-1]:
            self.tool_lines[-1] = label
        else:
            self.tool_lines.append(label)
        if len(self.tool_lines) > 8:
            self.tool_lines = self.tool_lines[-8:]

    def has_visible_output(
        self,
        *,
        thinking_display: ThinkingDisplay = "none",
    ) -> bool:
        if self.assistant_text or self.tool_lines:
            return True
        if thinking_display == "preview" and self.thinking_text.strip():
            return True
        if thinking_display == "count" and self.thinking_chars > 0:
            return True
        return False

    def _thinking_section(
        self,
        *,
        thinking_display: ThinkingDisplay,
        preview_max: int,
    ) -> str:
        if self.assistant_text:
            return ""
        if thinking_display == "preview" and self.thinking_text.strip():
            return format_thinking_preview(
                self.thinking_text,
                max_chars=preview_max,
            )
        if thinking_display == "count" and self.thinking_chars > 0:
            return format_thinking_line(self.thinking_chars)
        return ""

    def render_body(
        self,
        max_chars: int = 3000,
        *,
        thinking_display: ThinkingDisplay = "none",
        preview_max: int = 300,
    ) -> str:
        parts: list[str] = []
        if self.tool_lines:
            parts.append("\n".join(self.tool_lines))
        thinking = self._thinking_section(
            thinking_display=thinking_display,
            preview_max=preview_max,
        )
        if thinking:
            parts.append(thinking)
        if self.assistant_text:
            parts.append(self.assistant_text)
        body = "\n\n".join(part for part in parts if part).strip()
        if len(body) > max_chars:
            body = "…\n" + body[-max_chars:]
        return body or EMPTY_STREAM_HINT
