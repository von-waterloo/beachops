"""Tests for prompt templates."""

from __future__ import annotations

from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.domain.prompts import ASK_SYSTEM_PREFIX, build_prompt, git_safety_prefix


def test_ask_mode_prepends_ask_system_prefix() -> None:
    text = build_prompt("что такое asyncio?", UserMode.ASK, default_branch="dev")
    assert text.startswith(ASK_SYSTEM_PREFIX.strip()[:20])
    assert "РЕЖИМ ЧАТ" in text
    assert "Не меняй" in text
    assert "2500 символов" in text
    assert "КРИТИЧНО — Git" not in text


def test_plan_mode_includes_git_safety() -> None:
    text = build_prompt("добавь логирование", UserMode.PLAN, default_branch="develop")
    assert "КРИТИЧНО — Git" in text
    assert "develop" in text
    assert "main" in text
    assert text.endswith("добавь логирование")


def test_do_mode_includes_git_safety() -> None:
    text = build_prompt("исправь баг", UserMode.DO, default_branch="dev")
    assert git_safety_prefix(default_branch="dev") in text
    assert text.endswith("исправь баг")


def test_ask_mode_with_memory_block() -> None:
    block = "[заметка] dev branch"
    text = build_prompt(
        "какая ветка?",
        UserMode.ASK,
        default_branch="dev",
        memory_block=block,
    )
    assert "Контекст из памяти" in text
    assert block in text
    assert "РЕЖИМ ЧАТ" in text


def test_ask_mode_dev_questionnaire_only_when_needed() -> None:
    assert "Опросник" in ASK_SYSTEM_PREFIX
    assert "разработку" in ASK_SYSTEM_PREFIX.lower()
    assert "опросник не нужен" in ASK_SYSTEM_PREFIX.lower()
