"""Tests for agent list inline keyboard layout."""

from __future__ import annotations

from tg_cursor_bot.domain.models import AgentSlot
from tg_cursor_bot.services.inline_keyboards import (
    AGENTS_PER_PAGE,
    CB_AGENT_DELETE_PREFIX,
    CB_AGENT_PAGE_PREFIX,
    CB_AGENT_PREFIX,
    CB_AGENT_RENAME_PREFIX,
    agent_slots_keyboard,
    paginate_agent_slots,
)


def _slot(slot_id: int, label: str, *, active: bool = False) -> AgentSlot:
    return AgentSlot(
        id=slot_id,
        tg_user_id=1,
        label=label,
        cursor_agent_id=None,
        repo_id=1,
        active_run_id=None,
        is_active=active,
        repo_alias="repo",
    )


def test_paginate_clamps_page() -> None:
    slots = [_slot(i, f"A{i}") for i in range(1, 11)]
    page_slots, page, total = paginate_agent_slots(slots, 99)
    assert len(page_slots) == 2
    assert page == 2
    assert total == 3


def test_keyboard_two_rows_per_agent() -> None:
    slots = [_slot(1, "Лиса", active=True), _slot(2, "Якорь")]
    markup = agent_slots_keyboard(slots, can_create=True, can_delete=True)
    # 2 agents × 2 rows + new agent row
    assert len(markup.inline_keyboard) == 5
    name_row, actions_row, name_row2, actions_row2, new_row = markup.inline_keyboard
    assert len(name_row) == 1
    assert "Лиса" in name_row[0].text
    assert name_row[0].callback_data == f"{CB_AGENT_PREFIX}1"
    assert len(actions_row) == 2
    assert actions_row[0].callback_data == f"{CB_AGENT_RENAME_PREFIX}1"
    assert actions_row[1].callback_data == f"{CB_AGENT_DELETE_PREFIX}1"
    assert new_row[0].text == "+ Новый агент"


def test_keyboard_pagination_nav() -> None:
    slots = [_slot(i, f"S{i}") for i in range(1, 10)]
    markup = agent_slots_keyboard(slots, page=1, can_create=False, can_delete=True)
    nav_row = markup.inline_keyboard[-1]
    assert len(nav_row) == 3
    assert nav_row[0].callback_data == f"{CB_AGENT_PAGE_PREFIX}0"
    assert "2 / 3" in nav_row[1].text
    assert nav_row[2].callback_data == f"{CB_AGENT_PAGE_PREFIX}2"
