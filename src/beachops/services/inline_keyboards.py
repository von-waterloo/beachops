"""Inline keyboard builders and callback_data constants."""

from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from beachops.domain.cursor_models import CURSOR_MODEL_ORDER, cursor_model_label
from beachops.domain.cursor_tokens import cursor_token_label
from beachops.domain.models import AgentSlot, RepoConfig, RunSummary, UserMode
from beachops.services.agent_slot_naming import slot_button_text
from beachops.services.ui_copy import MODE_LABELS

CB_CANCEL = "cancel_run"
CB_REPO_PREFIX = "repo:"
CB_MODE_PREFIX = "mode:"
CB_MODEL_PREFIX = "model:"
CB_TOKEN_PREFIX = "token:"
CB_RETRY_PREFIX = "retry:"
CB_NAV_REPO = "nav:repo"
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
CB_BUILD_PLAN = "plan:build"
CB_JOB_APPROVE_PREFIX = "j:a:"
CB_JOB_REJECT_PREFIX = "j:r:"
CB_JOB_REVISION_PREFIX = "j:v:"
CB_ROLLBACK_PREFIX = "j:rb:"
CB_VOICE_CONFIRM_PREFIX = "vc:"
CB_VOICE_CANCEL_PREFIX = "vx:"

# Two rows per agent (name + actions); paginates within Telegram UI limits
# regardless of AGENT_SLOTS_MAX (settings, range 5-10).
AGENTS_PER_PAGE = 4


def dashboard_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎛 Агенты", web_app=WebAppInfo(url=url))]]
    )


def job_approval_keyboard(
    *,
    approve_token: str,
    reject_token: str,
    revision_token: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "Одобрить",
                callback_data=f"{CB_JOB_APPROVE_PREFIX}{approve_token}",
            ),
            InlineKeyboardButton(
                "Отклонить",
                callback_data=f"{CB_JOB_REJECT_PREFIX}{reject_token}",
            ),
        ]
    ]
    if revision_token:
        rows.append(
            [
                InlineKeyboardButton(
                    "Запросить доработку",
                    callback_data=f"{CB_JOB_REVISION_PREFIX}{revision_token}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def rollback_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Откатить прод на этот SHA",
                    callback_data=f"{CB_ROLLBACK_PREFIX}{token}",
                )
            ]
        ]
    )


def voice_confirmation_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Отправить в BeachOps",
                    callback_data=f"{CB_VOICE_CONFIRM_PREFIX}{draft_id}",
                ),
                InlineKeyboardButton(
                    "Отмена",
                    callback_data=f"{CB_VOICE_CANCEL_PREFIX}{draft_id}",
                ),
            ]
        ]
    )


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
    return [InlineKeyboardButton("✖️ Отменить", callback_data=CB_CANCEL)]


def _mode_buttons(*, is_admin: bool, current: UserMode) -> list[InlineKeyboardButton]:
    modes = [UserMode.ASK]
    if is_admin:
        modes.extend([UserMode.PLAN, UserMode.DO])

    row: list[InlineKeyboardButton] = []
    for mode in modes:
        label = MODE_LABELS.get(mode.value, mode.value).capitalize()
        # Leading checkmark + no emoji — keeps "✓ Действие" visible on narrow screens.
        prefix = "✓ " if mode == current else ""
        row.append(
            InlineKeyboardButton(
                f"{prefix}{label}",
                callback_data=f"{CB_MODE_PREFIX}{mode.value}",
            )
        )
    return row


_MODEL_BUTTONS_PER_ROW = 2


def _model_buttons(
    *,
    current_model_key: str,
    model_options: Sequence[tuple[str, str]] | None = None,
) -> list[list[InlineKeyboardButton]]:
    """Model choices as a 2-per-row grid with versioned labels."""
    buttons: list[InlineKeyboardButton] = []
    if model_options:
        choices = list(model_options)
    else:
        choices = [(choice.value, cursor_model_label(choice.value)) for choice in CURSOR_MODEL_ORDER]
    for key, label in choices:
        prefix = "✓ " if key == current_model_key else ""
        # Telegram callback_data max 64 bytes — fingerprints stay short.
        callback = f"{CB_MODEL_PREFIX}{key}"
        if len(callback.encode("utf-8")) > 64:
            continue
        buttons.append(
            InlineKeyboardButton(
                f"{prefix}{label}"[:64],
                callback_data=callback,
            )
        )
    return [
        buttons[i : i + _MODEL_BUTTONS_PER_ROW]
        for i in range(0, len(buttons), _MODEL_BUTTONS_PER_ROW)
    ]


def _token_buttons(
    *,
    current_token_key: str | None,
    available_token_keys: Sequence[str] | None = None,
) -> list[list[InlineKeyboardButton]]:
    """Token switch row; hidden when no extra keys are configured."""
    if current_token_key is None or not available_token_keys:
        return []
    row: list[InlineKeyboardButton] = []
    for key in available_token_keys:
        prefix = "✓ " if key == current_token_key else ""
        row.append(
            InlineKeyboardButton(
                f"{prefix}🔑 {cursor_token_label(key)}",
                callback_data=f"{CB_TOKEN_PREFIX}{key}",
            )
        )
    return [row]


def status_reply_markup(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    has_repos: bool,
    current_token_key: str | None = None,
    available_token_keys: Sequence[str] | None = None,
    model_options: Sequence[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    rows = [_mode_buttons(is_admin=is_admin, current=current)]
    rows.extend(
        _model_buttons(
            current_model_key=current_model_key,
            model_options=model_options,
        )
    )
    rows.extend(
        _token_buttons(
            current_token_key=current_token_key,
            available_token_keys=available_token_keys,
        )
    )
    rows.extend(status_nav_keyboard(has_repos=has_repos).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def run_activity_keyboard(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    current_token_key: str | None = None,
) -> InlineKeyboardMarkup:
    """Compact controls while a run is active — mode/model via /status."""
    return InlineKeyboardMarkup([_cancel_row()])


def post_run_keyboard(
    *,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    current_token_key: str | None = None,
    available_token_keys: Sequence[str] | None = None,
    with_retry: bool = False,
    with_build_plan: bool = False,
    model_options: Sequence[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    """Compact post-run controls — mode/model/token switch via /status."""
    del current, current_model_key, current_token_key, available_token_keys, model_options
    rows: list[list[InlineKeyboardButton]] = []
    if with_build_plan and is_admin:
        rows.append(
            [InlineKeyboardButton("▶️ Выполнить план", callback_data=CB_BUILD_PLAN)]
        )
    if with_retry:
        rows.append([InlineKeyboardButton("Повторить", callback_data=CB_RETRY_LAST)])
    return InlineKeyboardMarkup(rows)


def welcome_keyboard(
    *,
    has_repos: bool,
    is_admin: bool,
    current: UserMode,
    current_model_key: str,
    current_token_key: str | None = None,
    available_token_keys: Sequence[str] | None = None,
    webapp_url: str | None = None,
    model_options: Sequence[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    url = (webapp_url or "").strip()
    if url.lower().startswith("https://"):
        rows.append(
            [InlineKeyboardButton("🎛 Агенты", web_app=WebAppInfo(url=url))]
        )
    rows.append(_mode_buttons(is_admin=is_admin, current=current))
    rows.extend(
        _model_buttons(
            current_model_key=current_model_key,
            model_options=model_options,
        )
    )
    rows.extend(
        _token_buttons(
            current_token_key=current_token_key,
            available_token_keys=available_token_keys,
        )
    )
    rows.extend(status_nav_keyboard(has_repos=has_repos).inline_keyboard)
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
                "✏️ Изменить",
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
    """Repo/Agents/Memory nav — Agents and Memory are always reachable,
    even before the user has added a repository."""
    repo_button = (
        InlineKeyboardButton("Репозитории", callback_data=CB_NAV_REPO)
        if has_repos
        else InlineKeyboardButton("Добавить репо", callback_data=CB_NAV_REPO_HINT)
    )
    return InlineKeyboardMarkup(
        [
            [repo_button, InlineKeyboardButton("Агенты", callback_data=CB_NAV_AGENTS)],
            [InlineKeyboardButton("Память", callback_data=CB_NAV_MEMORY)],
        ]
    )


def memory_keyboard(items: list[RunSummary]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
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
