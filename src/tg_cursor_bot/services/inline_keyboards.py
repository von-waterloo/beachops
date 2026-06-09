"""Inline keyboard builders and callback_data constants."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from tg_cursor_bot.domain.cursor_models import CURSOR_MODEL_ORDER, cursor_model_label
from tg_cursor_bot.domain.models import AgentSlot, RepoConfig, RunSummary, UserMode
from tg_cursor_bot.services.agent_slot_naming import slot_button_text
from tg_cursor_bot.services.ui_copy import MODE_ICONS, MODE_LABELS

CB_CANCEL = "cancel_run"
CB_REPO_PREFIX = "repo:"
CB_MODE_PREFIX = "mode:"
CB_MODEL_PREFIX = "model:"
CB_RETRY_PREFIX = "retry:"
CB_NAV_REPO = "nav:repo"
CB_NAV_MODE = "nav:mode"
CB_NAV_MEMORY = "nav:memory"
CB_NAV_AGENTS = "nav:agents"
CB_NAV_REPO_HINT = "nav:repo_hint"
CB_AGENT_PREFIX = "agent:"
CB_AGENT_PAGE_PREFIX = "agent:page:"
CB_AGENT_RENAME_PREFIX = "agent:rename:"
CB_AGENT_DELETE_PREFIX = "agent:del:"
CB_AGENT_DELETE_CONFIRM_PREFIX = "agent:del:yes:"
CB_AGENT_DELETE_CANCEL = "agent:del:no"
CB_AGENT_NEW = "agent:new"
CB_RETRY_LAST = "retry:last"

# Two rows per agent (name + actions); keeps max slots (10) within Telegram UI limits.
AGENTS_PER_PAGE = 4


def paginate_agent_slots(
    slots: list[AgentSlot], page: int
) -> tuple[list[AgentSlot], int, int]:
    """Return (slots on page, clamped page index, total pages)."""
    if not slots:
        return [], 0, 1
    total_pages = (len(slots) + AGENTS_PER_PAGE - 1) // AGENTS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    start = page * AGENTS_PER_PAGE
    return slots[start : start + AGENTS_PER_PAGE], page, total_pages


def _cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("Отменить", callback_data=CB_CANCEL)]


def _mode_buttons(*, is_admin: bool, current: UserMode) -> list[InlineKeyboardButton]:
    modes = [UserMode.ASK]
    if is_admin:
        modes.extend([UserMode.PLAN, UserMode.DO])

    row: list[InlineKeyboardButton] = []
    for mode in modes:
        icon = MODE_ICONS.get(mode.value, "")
        label = MODE_LABELS.get(mode.value, mode.value).capitalize()
        suffix = " ✓" if mode == current else ""
        row.append(
            InlineKeyboardButton(
                f"{icon} {label}{suffix}",
                callback_data=f"{CB_MODE_PREFIX}{mode.value}",
            )
        )
    return row


def _model_buttons(*, current_model_key: str) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    for choice in CURSOR_MODEL_ORDER:
        label = cursor_model_label(choice.value)
        suffix = " ✓" if choice.value == current_model_key else ""
        row.append(
            InlineKeyboardButton(
                f"{label}{suffix}",
                callback_data=f"{CB_MODEL_PREFIX}{choice.value}",
            )
        )
    return row


def mode_keyboard(*, is_admin: bool, current: UserMode) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([_mode_buttons(is_admin=is_admin, current=current)])


def status_reply_markup(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    has_repos: bool,
) -> InlineKeyboardMarkup:
    rows = [
        _mode_buttons(is_admin=is_admin, current=current),
        _model_buttons(current_model_key=current_model_key),
    ]
    rows.extend(status_nav_keyboard(has_repos=has_repos).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def run_activity_keyboard(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            _mode_buttons(is_admin=is_admin, current=current),
            _model_buttons(current_model_key=current_model_key),
            _cancel_row(),
        ]
    )


def post_run_keyboard(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    with_retry: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        _mode_buttons(is_admin=is_admin, current=current),
        _model_buttons(current_model_key=current_model_key),
    ]
    if with_retry:
        rows.append([InlineKeyboardButton("Повторить", callback_data=CB_RETRY_LAST)])
    return InlineKeyboardMarkup(rows)


def welcome_keyboard(
    *,
    has_repos: bool,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
) -> InlineKeyboardMarkup:
    rows = [
        _mode_buttons(is_admin=is_admin, current=current),
        _model_buttons(current_model_key=current_model_key),
    ]
    if has_repos:
        rows.append(
            [
                InlineKeyboardButton("Репозитории", callback_data=CB_NAV_REPO),
                InlineKeyboardButton("Агенты", callback_data=CB_NAV_AGENTS),
            ]
        )
        rows.append([InlineKeyboardButton("Память", callback_data=CB_NAV_MEMORY)])
    else:
        rows.append(
            [InlineKeyboardButton("Как добавить репо", callback_data=CB_NAV_REPO_HINT)]
        )
    return InlineKeyboardMarkup(rows)


def repo_list_keyboard(repos: list[RepoConfig]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for repo in repos:
        mark = " ·" if repo.is_active else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{repo.alias}{mark}",
                    callback_data=f"{CB_REPO_PREFIX}{repo.alias}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def agent_slots_keyboard(
    slots: list[AgentSlot],
    *,
    page: int = 0,
    can_create: bool,
    can_delete: bool = True,
) -> InlineKeyboardMarkup:
    page_slots, page, total_pages = paginate_agent_slots(slots, page)
    rows: list[list[InlineKeyboardButton]] = []
    for slot in page_slots:
        rows.append(
            [
                InlineKeyboardButton(
                    slot_button_text(slot.label, is_active=slot.is_active, max_len=42),
                    callback_data=f"{CB_AGENT_PREFIX}{slot.id}",
                )
            ]
        )
        actions: list[InlineKeyboardButton] = [
            InlineKeyboardButton(
                "✏️ Редактировать",
                callback_data=f"{CB_AGENT_RENAME_PREFIX}{slot.id}",
            ),
        ]
        if can_delete:
            actions.append(
                InlineKeyboardButton(
                    "🗑 Удалить",
                    callback_data=f"{CB_AGENT_DELETE_PREFIX}{slot.id}",
                )
            )
        rows.append(actions)

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    "◀ Назад",
                    callback_data=f"{CB_AGENT_PAGE_PREFIX}{page - 1}",
                )
            )
        nav.append(
            InlineKeyboardButton(
                f"· {page + 1} / {total_pages} ·",
                callback_data=f"{CB_AGENT_PAGE_PREFIX}{page}",
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    "Вперёд ▶",
                    callback_data=f"{CB_AGENT_PAGE_PREFIX}{page + 1}",
                )
            )
        rows.append(nav)

    if can_create:
        rows.append([InlineKeyboardButton("+ Новый агент", callback_data=CB_AGENT_NEW)])
    return InlineKeyboardMarkup(rows)


def agent_delete_confirm_keyboard(slot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🗑 Удалить",
                    callback_data=f"{CB_AGENT_DELETE_CONFIRM_PREFIX}{slot_id}",
                ),
                InlineKeyboardButton("Отмена", callback_data=CB_AGENT_DELETE_CANCEL),
            ]
        ]
    )


def status_nav_keyboard(*, has_repos: bool) -> InlineKeyboardMarkup:
    if not has_repos:
        return InlineKeyboardMarkup([])
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Репозитории", callback_data=CB_NAV_REPO),
                InlineKeyboardButton("Агенты", callback_data=CB_NAV_AGENTS),
            ],
            [InlineKeyboardButton("Память", callback_data=CB_NAV_MEMORY)],
        ]
    )


def memory_keyboard(items: list[RunSummary]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:5]:
        row: list[InlineKeyboardButton] = [
            InlineKeyboardButton(
                f"↻ #{item.id}",
                callback_data=f"{CB_RETRY_PREFIX}{item.id}",
            )
        ]
        if item.pr_url:
            row.append(InlineKeyboardButton("PR", url=item.pr_url))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Повторить", callback_data=CB_RETRY_LAST)]]
    )
