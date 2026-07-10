"""Tests for agent slot naming."""

from beachops.domain.models import RepoConfig
from beachops.services.agent_slot_naming import (
    RANDOM_SLOT_LABELS,
    default_slot_label,
    is_auto_slot_label,
    label_from_prompt,
    random_slot_label,
    slot_button_text,
)
from beachops.services.forward_format import format_user_text_block, join_prompt_blocks
from beachops.services.ui_copy import forward_context_default_prompt


def test_random_pool_has_100_unique_labels():
    assert len(RANDOM_SLOT_LABELS) == 100
    assert len(set(RANDOM_SLOT_LABELS)) == 100


def test_random_slot_label_from_pool():
    assert random_slot_label() in RANDOM_SLOT_LABELS


def test_default_slot_label_uses_random_pool():
    label = default_slot_label(_repo(), 2)
    assert label in RANDOM_SLOT_LABELS


def _repo(alias: str = "AI-ContentMaker") -> RepoConfig:
    return RepoConfig(
        id=1,
        tg_user_id=1,
        alias=alias,
        github_url="https://github.com/x/y",
        default_branch="dev",
        is_active=True,
    )


def test_is_auto_slot_label():
    assert is_auto_slot_label("Лиса")
    assert is_auto_slot_label("AI-ContentMaker #2")
    assert is_auto_slot_label("Агент 3")
    assert is_auto_slot_label("Основной")
    assert not is_auto_slot_label("Метрика — баг")


def test_label_from_plain_prompt():
    assert label_from_prompt("  Fix yandex metric\nrest") == "Fix yandex metric"


def test_label_from_prompt_skips_short_and_instruction():
    assert label_from_prompt("привет") is None
    assert label_from_prompt(forward_context_default_prompt()) is None


def test_label_from_prompt_prefers_user_block():
    blocks = [
        "[Forwarded · chat · 2026-01-01 00:00 UTC]\nстарый текст",
        forward_context_default_prompt(),
        format_user_text_block("Fix yandex metric in dashboard"),
    ]
    prompt = join_prompt_blocks(blocks)
    assert label_from_prompt(prompt) == "Fix yandex metric in dashboard"


def test_label_from_prompt_uses_forward_body_without_user_text():
    blocks = [
        "[Forwarded · @dev · 2026-01-01 00:00 UTC]\nПропала метрика в отчёте",
        forward_context_default_prompt(),
    ]
    prompt = join_prompt_blocks(blocks)
    assert label_from_prompt(prompt) == "Пропала метрика в отчёте"


def test_slot_button_text_truncates():
    long_name = "Очень длинное имя агента для проверки обрезки"
    text = slot_button_text(long_name, is_active=True)
    assert text.endswith("✓")
    assert len(text) <= 30
