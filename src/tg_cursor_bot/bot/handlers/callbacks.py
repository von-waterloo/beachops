"""Inline callback query handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from tg_cursor_bot.app_context import AppContext
from tg_cursor_bot.domain.cursor_models import CursorModelKey, normalize_cursor_model_key
from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.services.cancel_service import cancel_user_work
from tg_cursor_bot.services.forward_context import clear_forward_context, get_forward_context_buffer
from tg_cursor_bot.bot.handlers.agent_list_ui import edit_agent_list_page, send_agent_list
from tg_cursor_bot.bot.handlers.agent_rename import start_agent_rename
from tg_cursor_bot.services.agent_rename_pending import clear_pending, peek_pending
from tg_cursor_bot.services.agent_slots import AgentSlotLastError, AgentSlotsFullError
from tg_cursor_bot.services.inline_keyboards import (
    CB_AGENT_DELETE_CANCEL,
    CB_AGENT_DELETE_CONFIRM_PREFIX,
    CB_AGENT_DELETE_PREFIX,
    CB_AGENT_NEW,
    CB_AGENT_PAGE_PREFIX,
    CB_AGENT_PREFIX,
    CB_AGENT_RENAME_PREFIX,
    CB_CANCEL,
    CB_MODE_PREFIX,
    CB_MODEL_PREFIX,
    CB_NAV_AGENTS,
    CB_NAV_MEMORY,
    CB_NAV_MODE,
    CB_NAV_REPO,
    CB_NAV_REPO_HINT,
    CB_REPO_PREFIX,
    CB_RETRY_LAST,
    CB_RETRY_PREFIX,
    agent_delete_confirm_keyboard,
    memory_keyboard,
    paginate_agent_slots,
    repo_list_keyboard,
    run_activity_keyboard,
    status_reply_markup,
)
from tg_cursor_bot.services.run_executor import (
    get_last_prompt,
    resolve_history_retry_mode,
    submit_user_prompt,
)
from tg_cursor_bot.services.ui_copy import (
    access_denied_mode,
    agent_delete_confirm,
    agent_delete_failed,
    agent_delete_last,
    agent_deleted,
    agent_created,
    agent_not_found,
    agent_slots_full,
    agent_switched,
    cancel_failed,
    cancel_inline_answer,
    cancel_none,
    cancel_ok,
    memory_empty,
    memory_header,
    memory_item_line,
    build_status_message,
    model_set,
    model_set_next,
    mode_set,
    mode_set_next,
    repo_add_hint,
    repo_empty,
    repo_list_header,
    repo_list_line,
    repo_not_found,
    repo_switched,
    retry_no_prompt,
)

logger = logging.getLogger(__name__)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    app: AppContext = context.application.bot_data["app"]
    user = query.from_user
    data = query.data

    if data == CB_CANCEL:
        await _handle_cancel(query, context, app, user.id)
        return

    if data == CB_NAV_REPO:
        await _show_repo_list(query, app, user.id)
        return

    if data == CB_NAV_MODE:
        await _show_mode_picker(query, app, user.id)
        return

    if data == CB_NAV_MEMORY:
        await _show_memory(query, app, user.id)
        return

    if data == CB_NAV_AGENTS:
        await _show_agent_list(query, app, user.id)
        return

    if data == CB_NAV_REPO_HINT:
        await query.answer()
        await query.message.reply_text(repo_add_hint(app.settings.default_branch))
        return

    if data.startswith(CB_REPO_PREFIX):
        await _handle_repo_select(query, app, user.id, data[len(CB_REPO_PREFIX) :])
        return

    if data == CB_AGENT_DELETE_CANCEL:
        await query.answer("Отменено")
        return

    if data.startswith(CB_AGENT_DELETE_CONFIRM_PREFIX):
        await _handle_agent_delete_confirm(query, context, app, user.id, data[len(CB_AGENT_DELETE_CONFIRM_PREFIX) :])
        return

    if data.startswith(CB_AGENT_DELETE_PREFIX):
        await _handle_agent_delete_prompt(query, app, user.id, data[len(CB_AGENT_DELETE_PREFIX) :])
        return

    if data == CB_AGENT_NEW:
        await _handle_agent_new(query, app, user.id)
        return

    if data.startswith(CB_AGENT_PAGE_PREFIX):
        await _handle_agent_page(query, app, user.id, data[len(CB_AGENT_PAGE_PREFIX) :])
        return

    if data.startswith(CB_AGENT_RENAME_PREFIX):
        await _handle_agent_rename(query, context, app, user.id, data[len(CB_AGENT_RENAME_PREFIX) :])
        return

    if data.startswith(CB_AGENT_PREFIX):
        await _handle_agent_select(query, app, user.id, data[len(CB_AGENT_PREFIX) :])
        return

    if data.startswith(CB_MODE_PREFIX):
        await _handle_mode_select(query, app, user.id, data[len(CB_MODE_PREFIX) :])
        return

    if data.startswith(CB_MODEL_PREFIX):
        await _handle_model_select(query, app, user.id, data[len(CB_MODEL_PREFIX) :])
        return

    if data.startswith(CB_RETRY_PREFIX):
        history_id = data[len(CB_RETRY_PREFIX) :]
        await _handle_retry(query, context, app, user.id, history_id)
        return

    if data == CB_RETRY_LAST:
        await _handle_retry_last(query, context, app, user.id)
        return

    await query.answer()


async def _handle_cancel(query, context, app: AppContext, user_id: int) -> None:
    slot = await app.agent_slots.get_active(user_id)
    pending = app.job_queue.pending_count(user_id)
    forward_count = get_forward_context_buffer(context).item_count(user_id)
    if (
        not (slot and slot.active_run_id)
        and not app.job_queue.is_active(user_id)
        and pending == 0
        and forward_count == 0
    ):
        await query.answer(cancel_none(), show_alert=True)
        return

    await query.answer(cancel_inline_answer())
    cleared_forward = await clear_forward_context(context, user_id)
    outcome = await cancel_user_work(app, user_id)

    if outcome.cancelled_run or outcome.cleared_queue or cleared_forward:
        is_admin = app.settings.is_admin(user_id)
        current = await app.users.get_mode(user_id)
        model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        repos = await app.repos.list_repos(user_id)
        try:
            await query.message.edit_reply_markup(
                reply_markup=status_reply_markup(
                    is_admin=is_admin,
                    current=current,
                    current_model_key=model_key,
                    has_repos=bool(repos),
                ),
            )
        except BadRequest:
            pass
        await query.message.reply_text(
            cancel_ok(cleared_queue=outcome.cleared_queue, cleared_forwards=cleared_forward),
        )
    else:
        await query.message.reply_text(cancel_failed())


async def _show_repo_list(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    repos = await app.repos.list_repos(user_id)
    if not repos:
        await query.message.reply_text(repo_empty(app.settings.default_branch))
        return

    lines = [repo_list_header(), ""]
    lines.extend(repo_list_line(r) for r in repos)
    await query.message.reply_text(
        "\n".join(lines),
        reply_markup=repo_list_keyboard(repos),
    )


async def _show_mode_picker(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    mode = await app.users.get_mode(user_id)
    model_key = await app.users.get_cursor_model_key(
        user_id, default=app.settings.cursor_model
    )
    repo = await app.repos.get_active_repo(user_id)
    slot = await app.agent_slots.ensure_default_slot(user_id)
    is_admin = app.settings.is_admin(user_id)
    repos = await app.repos.list_repos(user_id)
    text = build_status_message(
        mode=mode,
        model_key=model_key,
        repo=repo,
        is_active=app.job_queue.is_active(user_id),
        pending_count=app.job_queue.pending_count(user_id),
        has_active_run=bool(slot.active_run_id),
        active_agent_label=slot.label,
    )
    await query.message.reply_text(
        text,
        reply_markup=status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
        ),
    )


async def _show_memory(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    items = await app.memory.list_recent(user_id)
    if not items:
        await query.message.reply_text(memory_empty())
        return

    runs = await app.memory.list_runs_for_retry(user_id)
    lines = [memory_header()]
    lines.extend(memory_item_line(item) for item in items)
    await query.message.reply_text(
        "\n".join(lines),
        reply_markup=memory_keyboard(runs),
    )


async def _handle_repo_select(query, app: AppContext, user_id: int, alias: str) -> None:
    repo = await app.repos.set_active(user_id, alias)
    if repo is None:
        await query.answer(repo_not_found(alias), show_alert=True)
        return

    await app.agent_slots.sync_active_slot_repo(user_id, repo)
    await query.answer(f"Репо · {repo.alias}")
    await query.message.reply_text(repo_switched(repo.alias))


async def _show_agent_list(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    assert query.message is not None
    await send_agent_list(
        bot=query.message.get_bot(),
        chat_id=query.message.chat_id,
        app=app,
        user_id=user_id,
    )


async def _handle_agent_page(
    query, app: AppContext, user_id: int, page_raw: str
) -> None:
    try:
        page = int(page_raw)
    except ValueError:
        await query.answer()
        return

    assert query.message is not None
    slots = await app.agent_slots.list_slots(user_id)
    _, page, total_pages = paginate_agent_slots(slots, page)
    if total_pages <= 1:
        await query.answer()
        return

    await query.answer()
    try:
        await edit_agent_list_page(
            message=query.message,
            app=app,
            user_id=user_id,
            page=page,
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _handle_agent_delete_prompt(query, app: AppContext, user_id: int, slot_id_raw: str) -> None:
    try:
        slot_id = int(slot_id_raw)
    except ValueError:
        await query.answer("Неверный агент", show_alert=True)
        return

    slots = await app.agent_slots.list_slots(user_id)
    if len(slots) <= 1:
        await query.answer(agent_delete_last(), show_alert=True)
        return

    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None:
        await query.answer(agent_not_found(), show_alert=True)
        return

    await query.answer()
    assert query.message is not None
    await query.message.reply_text(
        agent_delete_confirm(slot.label),
        reply_markup=agent_delete_confirm_keyboard(slot_id),
    )


async def _handle_agent_delete_confirm(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
    slot_id_raw: str,
) -> None:
    try:
        slot_id = int(slot_id_raw)
    except ValueError:
        await query.answer("Неверный агент", show_alert=True)
        return

    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None:
        await query.answer(agent_not_found(), show_alert=True)
        return

    deleted_label = slot.label
    active = await app.agent_slots.get_active(user_id)
    if active is not None and active.id == slot_id:
        if (
            active.active_run_id
            or app.job_queue.is_active(user_id)
            or app.job_queue.pending_count(user_id) > 0
        ):
            await cancel_user_work(app, user_id)

    if peek_pending(context) == slot_id:
        clear_pending(context)

    try:
        new_active = await app.agent_slots.delete_slot(user_id, slot_id)
    except AgentSlotLastError:
        await query.answer(agent_delete_last(), show_alert=True)
        return

    if new_active is None:
        await query.answer(agent_delete_failed(), show_alert=True)
        return

    await query.answer("Удалено")
    assert query.message is not None
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except BadRequest:
        pass

    await query.message.reply_text(
        agent_deleted(
            deleted_label,
            new_active_label=new_active.label if slot.is_active else None,
        ),
    )
    await send_agent_list(
        bot=query.message.get_bot(),
        chat_id=query.message.chat_id,
        app=app,
        user_id=user_id,
    )


async def _handle_agent_rename(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
    slot_id_raw: str,
) -> None:
    try:
        slot_id = int(slot_id_raw)
    except ValueError:
        await query.answer("Неверный агент", show_alert=True)
        return

    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None:
        await query.answer(agent_not_found(), show_alert=True)
        return

    await query.answer()
    assert query.message is not None
    await start_agent_rename(
        context=context,
        chat_id=query.message.chat_id,
        bot=query.message.get_bot(),
        slot_id=slot_id,
        current_label=slot.label,
    )


async def _handle_agent_select(query, app: AppContext, user_id: int, slot_id_raw: str) -> None:
    try:
        slot_id = int(slot_id_raw)
    except ValueError:
        await query.answer("Неверный агент", show_alert=True)
        return

    slot = await app.agent_slots.activate_slot(user_id, slot_id)
    if slot is None:
        await query.answer(agent_not_found(), show_alert=True)
        return

    await query.answer(f"Агент · {slot.label}")
    await query.message.reply_text(agent_switched(slot.label))


async def _handle_agent_new(query, app: AppContext, user_id: int) -> None:
    try:
        slot = await app.agent_slots.create_new_slot(user_id)
    except AgentSlotsFullError:
        await query.answer(agent_slots_full(app.agent_slots.max_slots), show_alert=True)
        return

    await query.answer(f"Агент · {slot.label}")
    await query.message.reply_text(agent_created(slot.label))


async def _handle_mode_select(query, app: AppContext, user_id: int, mode_value: str) -> None:
    try:
        mode = UserMode(mode_value)
    except ValueError:
        await query.answer("Неизвестный режим", show_alert=True)
        return

    if not app.settings.can_use_mode(user_id, mode):
        from tg_cursor_bot.services.ui_copy import access_denied_mode

        await query.answer(access_denied_mode(mode), show_alert=True)
        return

    await app.users.set_mode(user_id, mode)
    is_admin = app.settings.is_admin(user_id)
    model_key = await app.users.get_cursor_model_key(
        user_id, default=app.settings.cursor_model
    )
    slot = await app.agent_slots.get_active(user_id)
    active_run = app.active_runs.get(user_id)
    has_work = (
        app.job_queue.is_active(user_id)
        or app.job_queue.pending_count(user_id) > 0
        or bool(slot and slot.active_run_id)
        or active_run is not None
    )
    toast = mode_set_next(mode) if has_work else mode_set(mode)
    await query.answer(toast)

    if active_run and active_run.message_id == query.message.message_id:
        markup = run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
        )
    else:
        repos = await app.repos.list_repos(user_id)
        markup = status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
        )
    await query.message.edit_reply_markup(reply_markup=markup)


async def _handle_model_select(query, app: AppContext, user_id: int, model_value: str) -> None:
    model_key = normalize_cursor_model_key(
        model_value, default=app.settings.cursor_model
    )
    if model_key not in {item.value for item in CursorModelKey}:
        await query.answer("Неизвестная модель", show_alert=True)
        return

    await app.users.set_cursor_model_key(user_id, model_key)
    is_admin = app.settings.is_admin(user_id)
    mode = await app.users.get_mode(user_id)
    slot = await app.agent_slots.get_active(user_id)
    active_run = app.active_runs.get(user_id)
    has_work = (
        app.job_queue.is_active(user_id)
        or app.job_queue.pending_count(user_id) > 0
        or bool(slot and slot.active_run_id)
        or active_run is not None
    )
    toast = model_set_next(model_key) if has_work else model_set(model_key)
    await query.answer(toast)

    if active_run and active_run.message_id == query.message.message_id:
        markup = run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
        )
    else:
        repos = await app.repos.list_repos(user_id)
        markup = status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
        )
    await query.message.edit_reply_markup(reply_markup=markup)


async def _handle_retry(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
    history_id: str,
) -> None:
    try:
        hid = int(history_id)
    except ValueError:
        await query.answer("Неверный id", show_alert=True)
        return

    item = await app.memory.get_run_by_id(user_id, hid)
    if item is None:
        await query.answer("Запись не найдена", show_alert=True)
        return

    mode = resolve_history_retry_mode(
        settings=app.settings,
        user_id=user_id,
        mode_value=item.mode,
    )
    if mode is None:
        try:
            denied = UserMode(item.mode or UserMode.ASK.value)
        except ValueError:
            denied = UserMode.ASK
        await query.answer(access_denied_mode(denied), show_alert=True)
        return

    await query.answer("Повторяю…")
    await submit_user_prompt(
        context=context,
        user_id=user_id,
        prompt=item.prompt_summary,
        mode=mode,
    )


async def _handle_retry_last(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
) -> None:
    prompt = get_last_prompt(app, user_id)
    if not prompt:
        await query.answer(retry_no_prompt(), show_alert=True)
        return

    await query.answer("Повторяю…")
    await submit_user_prompt(context=context, user_id=user_id, prompt=prompt)
