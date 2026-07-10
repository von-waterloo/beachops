"""Tests for prompt templates."""

from __future__ import annotations

from beachops.domain.models import UserMode
from beachops.domain.prompts import (
    ASK_SYSTEM_PREFIX,
    PLAN_SYSTEM_PREFIX,
    build_prompt,
    git_safety_prefix,
    is_protected_default_branch,
    server_ssh_block,
)


def test_ask_mode_prepends_ask_system_prefix() -> None:
    text = build_prompt("что такое asyncio?", UserMode.ASK, default_branch="dev")
    assert text.startswith(ASK_SYSTEM_PREFIX.strip()[:20])
    assert "РЕЖИМ ЧАТ" in text
    assert "репозиторий не меняй" in text
    assert "2500 символов" in text
    assert "не гадай" in text
    assert "Правила write-run" not in text
    assert text.endswith("что такое asyncio?")


def test_plan_mode_uses_plan_prefix_without_git_safety() -> None:
    text = build_prompt("добавь логирование", UserMode.PLAN, default_branch="develop")
    assert "РЕЖИМ ПЛАН" in text
    assert "Код не меняй" in text
    assert "переиспользу" in text.lower()
    assert "Объём плана" in text
    # План не пишет в репозиторий — git-safety не нужен.
    assert "Правила write-run" not in text
    assert text.endswith("добавь логирование")


def test_plan_prefix_mentions_telegram_constraints() -> None:
    assert "Telegram" in PLAN_SYSTEM_PREFIX
    assert "mermaid" in PLAN_SYSTEM_PREFIX
    assert "миграци" in PLAN_SYSTEM_PREFIX.lower()


def test_do_mode_includes_git_safety_and_guidance() -> None:
    text = build_prompt("исправь баг", UserMode.DO, default_branch="dev")
    assert git_safety_prefix(default_branch="dev") in text
    assert "Переиспользуй" in text
    assert "не раздувай scope" in text
    assert "делай сразу и смело" in text
    assert "кайф" in text
    assert "Миграции БД не запускай" in text
    assert "project-skills" in text
    assert "add-bot-feature" in text
    assert "Рабочая база" in text
    assert "Не merge" in text
    assert "production БД" in text
    assert "произвольные команды из Telegram не исполняй" in text
    assert text.endswith("исправь баг")


def test_plan_prefix_mentions_project_skills() -> None:
    assert "project-skills" in PLAN_SYSTEM_PREFIX
    assert ".cursor/skills" in PLAN_SYSTEM_PREFIX


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


def test_plan_mode_with_memory_block() -> None:
    block = "[запуск] прошлый план"
    text = build_prompt(
        "спланируй фичу",
        UserMode.PLAN,
        default_branch="dev",
        memory_block=block,
    )
    assert "Контекст из памяти" in text
    assert "РЕЖИМ ПЛАН" in text


def test_ask_mode_dev_questionnaire_only_when_needed() -> None:
    assert "A/B/C" in ASK_SYSTEM_PREFIX
    assert "разработку" in ASK_SYSTEM_PREFIX.lower()
    assert "прямой ответ" in ASK_SYSTEM_PREFIX.lower()


def test_plan_mode_asks_clarifying_questions_with_limit() -> None:
    assert "A/B/C" in PLAN_SYSTEM_PREFIX
    assert "до 3" in PLAN_SYSTEM_PREFIX
    assert "без допросов" in PLAN_SYSTEM_PREFIX


def test_ask_mode_prefers_freeform_chat() -> None:
    assert "как в мессенджере" in ASK_SYSTEM_PREFIX
    assert "Глубина = сложности" in ASK_SYSTEM_PREFIX
    assert "отчётных шаблонов" in ASK_SYSTEM_PREFIX


def test_protected_default_branches() -> None:
    assert is_protected_default_branch("main")
    assert is_protected_default_branch("Master")
    assert not is_protected_default_branch("dev")
    assert not is_protected_default_branch("develop")


def test_server_ssh_block_mentions_readonly_docker_only() -> None:
    block = server_ssh_block(label="prod")
    assert "AGENT_SSH_HOST" in block
    assert "AGENT_SSH_PRIVATE_KEY_B64" in block
    assert "docker ps" in block
    assert "Запрещено" in block
    assert "exec" in block


def test_server_ssh_block_adds_remote_dir_note() -> None:
    block = server_ssh_block(label="prod", remote_dir="/home/const/tg-cursor-bot")
    assert "/home/const/tg-cursor-bot" in block
    assert "AGENT_SSH_REMOTE_DIR" in block


def test_server_ssh_block_without_remote_dir_has_no_cd_note() -> None:
    block = server_ssh_block(label="prod")
    assert "AGENT_SSH_REMOTE_DIR" not in block


def test_do_mode_includes_server_ssh_note_when_provided() -> None:
    note = server_ssh_block(label="prod")
    text = build_prompt("проверь логи бота", UserMode.DO, default_branch="dev", server_ssh_note=note)
    assert "SSH-доступ для диагностики" in text
    assert text.endswith("проверь логи бота")


def test_do_mode_without_server_ssh_note_stays_clean() -> None:
    text = build_prompt("исправь баг", UserMode.DO, default_branch="dev")
    assert "SSH-доступ для диагностики" not in text


def test_ask_mode_includes_server_ssh_note_when_provided() -> None:
    note = server_ssh_block(label="dev")
    text = build_prompt("почему бот падает?", UserMode.ASK, default_branch="dev", server_ssh_note=note)
    assert "SSH-доступ для диагностики" in text


def test_plan_mode_never_includes_server_ssh_note() -> None:
    note = server_ssh_block(label="prod")
    text = build_prompt("спланируй фичу", UserMode.PLAN, default_branch="dev", server_ssh_note=note)
    assert "SSH-доступ для диагностики" not in text
