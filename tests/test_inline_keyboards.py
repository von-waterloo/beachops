"""Tests for mode/model inline keyboard layout."""

from __future__ import annotations

from beachops.domain.cursor_models import CursorModelKey
from beachops.domain.models import UserMode
from beachops.services.inline_keyboards import (
    CB_AGENT_DELETE_CANCEL,
    CB_BUILD_PLAN,
    CB_CANCEL,
    CB_MODE_PREFIX,
    CB_MODEL_PREFIX,
    CB_NAV_AGENTS,
    CB_NAV_MEMORY,
    CB_NAV_REPO,
    CB_NAV_REPO_HINT,
    CB_TOKEN_PREFIX,
    agent_delete_confirm_keyboard,
    post_run_keyboard,
    run_activity_keyboard,
    status_nav_keyboard,
    status_reply_markup,
    welcome_keyboard,
)


def test_mode_buttons_leading_checkmark_no_icons() -> None:
    markup = status_reply_markup(
        is_admin=True,
        current=UserMode.PLAN,
        current_model_key=CursorModelKey.FABLE_5.value,
        has_repos=False,
    )
    mode_row = markup.inline_keyboard[0]
    assert len(mode_row) == 3
    assert mode_row[0].text == "Чат"
    assert mode_row[1].text == "✓ План"
    assert mode_row[1].callback_data == f"{CB_MODE_PREFIX}plan"
    assert mode_row[2].text == "Действие"
    assert mode_row[2].callback_data == f"{CB_MODE_PREFIX}do"
    assert all("❓" not in b.text and "📋" not in b.text and "⚡" not in b.text for b in mode_row)


def test_model_buttons_are_two_per_row_grid() -> None:
    markup = status_reply_markup(
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        has_repos=False,
    )
    # row 0 = mode buttons, rows 1-2 = model buttons (2x2 grid)
    model_row_1, model_row_2 = markup.inline_keyboard[1], markup.inline_keyboard[2]
    assert len(model_row_1) == 2
    assert len(model_row_2) == 2

    all_model_buttons = [*model_row_1, *model_row_2]
    assert {b.callback_data for b in all_model_buttons} == {
        f"{CB_MODEL_PREFIX}{key.value}" for key in CursorModelKey
    }


def test_selected_model_button_has_leading_checkmark_and_version() -> None:
    markup = status_reply_markup(
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        has_repos=False,
    )
    all_buttons = [b for row in markup.inline_keyboard[1:3] for b in row]
    selected = next(
        b for b in all_buttons if b.callback_data == f"{CB_MODEL_PREFIX}{CursorModelKey.FABLE_5.value}"
    )
    assert selected.text == "✓ Fable 5"

    others = [b for b in all_buttons if b is not selected]
    assert {b.text for b in others} == {
        "Composer 2.5",
        "Sonnet 5",
        "GPT-5.6 Terra",
    }
    assert all(len(b.text) <= 14 for b in all_buttons)


def test_run_activity_keyboard_only_cancel() -> None:
    markup = run_activity_keyboard(
        is_admin=True,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
    )
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 1
    assert buttons[0].callback_data == CB_CANCEL


def test_post_run_keyboard_has_no_cancel() -> None:
    markup = post_run_keyboard(
        is_admin=True,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        with_retry=True,
        with_build_plan=True,
    )
    callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert CB_CANCEL not in callbacks


def test_post_run_keyboard_build_plan_button_for_admin() -> None:
    markup = post_run_keyboard(
        is_admin=True,
        current=UserMode.PLAN,
        current_model_key=CursorModelKey.FABLE_5.value,
        with_build_plan=True,
    )
    buttons = [b for row in markup.inline_keyboard for b in row]
    build = next(b for b in buttons if b.callback_data == CB_BUILD_PLAN)
    assert build.text == "▶️ Выполнить план"


def test_post_run_keyboard_no_build_plan_for_non_admin() -> None:
    markup = post_run_keyboard(
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        with_build_plan=True,
    )
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert all(b.callback_data != CB_BUILD_PLAN for b in buttons)


def test_token_row_hidden_without_second_token() -> None:
    markup = status_reply_markup(
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        has_repos=False,
    )
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert all(not (b.callback_data or "").startswith(CB_TOKEN_PREFIX) for b in buttons)


def test_token_row_shows_mt_and_mt2_with_checkmark() -> None:
    markup = status_reply_markup(
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
        has_repos=False,
        current_token_key="mt2",
    )
    token_buttons = [
        b
        for row in markup.inline_keyboard
        for b in row
        if (b.callback_data or "").startswith(CB_TOKEN_PREFIX)
    ]
    assert [b.callback_data for b in token_buttons] == [
        f"{CB_TOKEN_PREFIX}mt",
        f"{CB_TOKEN_PREFIX}mt2",
    ]
    assert token_buttons[0].text == "🔑 mt"
    assert token_buttons[1].text == "✓ 🔑 mt2"


def test_status_nav_keyboard_always_exposes_agents_and_memory() -> None:
    """Even brand-new users without a repo should be able to reach Agents/Memory."""
    markup = status_nav_keyboard(has_repos=False)
    buttons = [b for row in markup.inline_keyboard for b in row]
    callbacks = {b.callback_data for b in buttons}
    assert CB_NAV_AGENTS in callbacks
    assert CB_NAV_MEMORY in callbacks
    assert CB_NAV_REPO_HINT in callbacks
    assert CB_NAV_REPO not in callbacks


def test_status_nav_keyboard_shows_repo_list_when_present() -> None:
    markup = status_nav_keyboard(has_repos=True)
    buttons = [b for row in markup.inline_keyboard for b in row]
    callbacks = {b.callback_data for b in buttons}
    assert CB_NAV_REPO in callbacks
    assert CB_NAV_REPO_HINT not in callbacks


def test_welcome_keyboard_reuses_status_nav_without_repos() -> None:
    markup = welcome_keyboard(
        has_repos=False,
        is_admin=False,
        current=UserMode.ASK,
        current_model_key=CursorModelKey.FABLE_5.value,
    )
    buttons = [b for row in markup.inline_keyboard for b in row]
    callbacks = {b.callback_data for b in buttons}
    assert CB_NAV_AGENTS in callbacks
    assert CB_NAV_MEMORY in callbacks


def test_agent_delete_cancel_uses_dedicated_callback() -> None:
    markup = agent_delete_confirm_keyboard(42)
    cancel_button = next(
        b for row in markup.inline_keyboard for b in row if b.callback_data == CB_AGENT_DELETE_CANCEL
    )
    assert cancel_button.text == "Отмена"
