"""Normalize Cursor/LLM markdown before Telegram entity conversion."""

from __future__ import annotations

import re

# Cursor code citation: ```startLine:endLine:path
_CURSOR_FENCE_RE = re.compile(
    r"```(\d+):(\d+):([^\n`]+)\n",
    re.MULTILINE,
)

# Relative markdown links (no http/https/tg scheme)
_RELATIVE_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?!https?://|tg://)([^)]+)\)",
)

# Autolink <path> without http(s)
_AUTO_LINK_RE = re.compile(
    r"<(?!(?:https?://|tg://))([^>\s]+)>",
)

_VALID_TELEGRAM_LINK_URL = re.compile(r"^https?://", re.IGNORECASE)

# Fenced code blocks with info string
_FENCE_BLOCK_RE = re.compile(
    r"```([^\n]*)\n(.*?)```",
    re.DOTALL,
)

# Strange info string on fence (not a simple language id)
_STRANGE_FENCE_INFO_RE = re.compile(r"[^\w#+\-.]")

# Headings
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Bold / italic
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")

# Inline code
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Markdown links (any scheme)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Table rows
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$", re.MULTILINE)


def make_telegram_safe_markdown(text: str) -> str:
    """Normalize Cursor-specific markdown for telegramify-markdown."""
    if not text:
        return text

    def _cursor_fence(match: re.Match[str]) -> str:
        path = match.group(3).strip()
        return f"```\n// {path}\n"

    text = _CURSOR_FENCE_RE.sub(_cursor_fence, text)

    def _relative_link(match: re.Match[str]) -> str:
        label, path = match.group(1), match.group(2).strip()
        display = path if not label or label == path else f"{label}: {path}"
        return f"`{display}`"

    text = _RELATIVE_LINK_RE.sub(_relative_link, text)

    def _auto_link(match: re.Match[str]) -> str:
        path = match.group(1).strip()
        return f"`{path}`"

    text = _AUTO_LINK_RE.sub(_auto_link, text)

    fence_count = text.count("```")
    if fence_count % 2 == 1:
        text = text.rstrip() + "\n```"

    return text


def strip_poison_markdown(text: str) -> str:
    """Aggressive second pass when convert() fails."""
    text = make_telegram_safe_markdown(text)

    def _flatten_fence(match: re.Match[str]) -> str:
        info = match.group(1).strip()
        body = match.group(2).strip()
        if info and _STRANGE_FENCE_INFO_RE.search(info):
            lines = [f"// {info}"] if info else []
            lines.extend(body.splitlines())
            return "\n".join(lines)
        return match.group(0)

    text = _FENCE_BLOCK_RE.sub(_flatten_fence, text)

    text = _TABLE_SEP_RE.sub("", text)

    def _table_row(match: re.Match[str]) -> str:
        inner = match.group(1)
        cells = [c.strip() for c in inner.split("|")]
        return "  ".join(c for c in cells if c)

    text = _TABLE_ROW_RE.sub(_table_row, text)

    return text


def readable_plain(text: str) -> str:
    """Strip markdown syntax for plain Telegram text (no entities)."""
    if not text:
        return text

    text = make_telegram_safe_markdown(text)

    def _fence_plain(match: re.Match[str]) -> str:
        body = match.group(2).strip()
        if not body:
            return ""
        return "\n".join(f"  {line}" for line in body.splitlines())

    text = _FENCE_BLOCK_RE.sub(_fence_plain, text)

    text = _HEADING_RE.sub(r"\2", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)

    def _link_plain(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2).strip()
        if label and url and label != url:
            return f"{label} ({url})"
        return label or url

    text = _LINK_RE.sub(_link_plain, text)

    text = _TABLE_SEP_RE.sub("", text)
    text = _TABLE_ROW_RE.sub(
        lambda m: "  ".join(c.strip() for c in m.group(1).split("|") if c.strip()),
        text,
    )

    return text.strip()


def is_valid_telegram_link_url(url: str | None) -> bool:
    """Telegram text_link requires http(s) URL."""
    if not url:
        return False
    return bool(_VALID_TELEGRAM_LINK_URL.match(url.strip()))
