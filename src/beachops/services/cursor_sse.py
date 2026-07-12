"""Server-Sent Events parser for Cursor Cloud Agents API v1 streams."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SseEvent:
    event: str
    data: dict[str, Any]
    id: str | None = None


def _parse_data(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    return payload if isinstance(payload, dict) else {"value": payload}


def iter_sse_blocks(buffer: str) -> tuple[list[tuple[str, str | None, str]], str]:
    """Split a raw SSE buffer into complete event blocks and leftover bytes."""
    parts = buffer.split("\n\n")
    if not buffer.endswith("\n\n"):
        leftover = parts[-1]
        blocks = parts[:-1]
    else:
        leftover = ""
        blocks = parts
    parsed: list[tuple[str, str | None, str]] = []
    for block in blocks:
        event_name = "message"
        event_id: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip() or "message"
            elif line.startswith("id:"):
                event_id = line[3:].strip() or None
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines or event_name != "message":
            parsed.append((event_name, event_id, "\n".join(data_lines)))
    return parsed, leftover


async def parse_sse_stream(
    byte_chunks: AsyncIterator[bytes],
) -> AsyncIterator[SseEvent]:
    """Yield typed SSE events from an async byte stream."""
    buffer = ""
    async for chunk in byte_chunks:
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        events, buffer = iter_sse_blocks(buffer)
        for event_name, event_id, raw_data in events:
            yield SseEvent(event=event_name, data=_parse_data(raw_data), id=event_id)
    if buffer.strip():
        events, _ = iter_sse_blocks(buffer + "\n\n")
        for event_name, event_id, raw_data in events:
            yield SseEvent(event=event_name, data=_parse_data(raw_data), id=event_id)


def normalize_run_status(status: str | None) -> str:
    """Map Cursor REST statuses to BeachOps lowercase run statuses."""
    value = (status or "").strip().lower()
    mapping = {
        "creating": "running",
        "running": "running",
        "in_progress": "running",
        "finished": "finished",
        "completed": "finished",
        "error": "error",
        "failed": "error",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "expired": "error",
    }
    return mapping.get(value, value or "running")


def extract_git_fields(payload: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    if not payload:
        return None, None
    git = payload.get("git") if isinstance(payload, Mapping) else None
    if not isinstance(git, Mapping):
        return None, None
    branches = git.get("branches")
    if not isinstance(branches, list):
        return None, None
    branch_name: str | None = None
    pr_url: str | None = None
    for item in branches:
        if not isinstance(item, Mapping):
            continue
        if not branch_name and item.get("branch"):
            branch_name = str(item["branch"])
        if item.get("prUrl") or item.get("pr_url"):
            pr_url = str(item.get("prUrl") or item.get("pr_url"))
            break
    return branch_name, pr_url
