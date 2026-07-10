"""Tests for plan extraction from Cursor plan-mode runs."""

from __future__ import annotations

from beachops.services.plan_format import (
    extract_plan_from_tool_args,
    plan_document_filename,
    plan_title,
    split_plan_frontmatter,
)

_ARTIFACT = """---
name: Add /ping command
overview: 'Добавить команду `/ping`.'
todos:
  - id: add-cmd
    content: Добавить обработчик
    status: pending
isProject: false
---
# Добавить команду /ping → pong

## Шаги

- Добавить обработчик
"""


def test_extract_plan_from_tool_args() -> None:
    assert extract_plan_from_tool_args({"plan": "# План\n..."}) == "# План\n..."
    assert extract_plan_from_tool_args({"plan": "   "}) is None
    assert extract_plan_from_tool_args({"other": 1}) is None
    assert extract_plan_from_tool_args(None) is None
    assert extract_plan_from_tool_args("строка") is None


def test_split_plan_frontmatter_extracts_name_and_body() -> None:
    name, body = split_plan_frontmatter(_ARTIFACT)
    assert name == "Add /ping command"
    assert body.startswith("# Добавить команду /ping")
    assert "---" not in body.split("\n")[0]


def test_split_plan_frontmatter_without_frontmatter() -> None:
    name, body = split_plan_frontmatter("# Просто план\n\nШаги")
    assert name is None
    assert body == "# Просто план\n\nШаги"


def test_plan_title_from_heading() -> None:
    assert plan_title("# Заголовок плана\n\nтело") == "Заголовок плана"
    assert plan_title("без заголовка") is None


def test_plan_document_filename() -> None:
    assert plan_document_filename("Add /ping command") == "Add_ping_command.md"
    assert plan_document_filename(None) == "plan.md"
    assert plan_document_filename("///") == "plan.md"
