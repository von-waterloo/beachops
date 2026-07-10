"""Extract and normalize plan markdown from Cursor plan-mode runs.

Cursor cloud agents in plan mode emit the plan via the `create_plan` tool
(full markdown in `args["plan"]`) and store an `artifacts/plans/*.plan.md`
artifact with a YAML frontmatter block. `result.result` contains only a
short intro phrase, so the plan must be captured separately.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

PLAN_TOOL_NAME = "create_plan"
PLAN_ARTIFACT_SUFFIX = ".plan.md"

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_NAME_LINE_RE = re.compile(r"^name:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)
_UNSAFE_FILENAME_RE = re.compile(r"[^\w\- ]+")


def extract_plan_from_tool_args(args: Any) -> str | None:
    """Plan markdown from a `create_plan` tool_call args payload."""
    if not isinstance(args, Mapping):
        return None
    plan = args.get("plan")
    if isinstance(plan, str) and plan.strip():
        return plan.strip()
    return None


def split_plan_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (plan name from frontmatter, body without frontmatter)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None, text.strip()
    name_match = _NAME_LINE_RE.search(match.group(1))
    name = name_match.group(1).strip() if name_match else None
    return name or None, text[match.end() :].strip()


_FIRST_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def plan_title(body: str) -> str | None:
    """Plan title from the first `# heading` of the markdown body."""
    match = _FIRST_HEADING_RE.search(body)
    return match.group(1).strip() if match else None


def plan_document_filename(name: str | None) -> str:
    """Safe .md filename for sending the plan as a Telegram document."""
    base = _UNSAFE_FILENAME_RE.sub("", name or "").strip().replace(" ", "_")
    return f"{base or 'plan'}.md"
