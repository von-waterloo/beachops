"""Inline callback query handlers."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.cursor_models import CursorModelKey, normalize_cursor_model_key
from beachops.domain.cursor_tokens import CursorTokenKey, normalize_cursor_token_key
from beachops.domain.models import UserMode
from beachops.domain.security import ApprovalDecision, ApprovalKind, JobStatus, Role
from beachops.services.approval_actions import approve_job, reject_job, request_revision
from beachops.services.cancel_service import cancel_user_work, cancel_was_successful
from beachops.services.cursor_token_ui import available_token_keys_for_ui, token_ui_pair
from beachops.services.forward_context import clear_forward_context, get_forward_context_buffer
from beachops.services.prompt_coalesce import clear_prompt_coalesce, get_prompt_coalesce
from beachops.bot.handlers.agent_list_ui import (
    build_agent_list_markup,
    build_agent_list_text,
    edit_agent_list_page,
    send_agent_list,
)
from beachops.bot.handlers.agent_rename import start_agent_rename
from beachops.services.agent_rename_pending import clear_pending, peek_pending
from beachops.services.agent_slots import AgentSlotLastError, AgentSlotsFullError
from beachops.services.memory_present import build_memory_list
from beachops.services.nav_message import edit_or_reply
from beachops.services.inline_keyboards import (
    CB_AGENT_DELETE_CANCEL,
    CB_BUILD_PLAN,
    CB_AGENT_DELETE_CONFIRM_PREFIX,
    CB_AGENT_DELETE_PREFIX,
    CB_AGENT_NEW,
    CB_AGENT_PAGE_PREFIX,
    CB_AGENT_PREFIX,
    CB_AGENT_RENAME_PREFIX,
    CB_CANCEL,
    CB_JOB_APPROVE_PREFIX,
    CB_JOB_REJECT_PREFIX,
    CB_JOB_REVISION_PREFIX,
    CB_MODE_PREFIX,
    CB_MODEL_PREFIX,
    CB_NAV_AGENTS,
    CB_NAV_MEMORY,
    CB_NAV_REPO,
    CB_NAV_REPO_HINT,
    CB_REPO_PREFIX,
    CB_RETRY_LAST,
    CB_RETRY_PREFIX,
    CB_TOKEN_PREFIX,
    CB_ROLLBACK_PREFIX,
    CB_VOICE_CANCEL_PREFIX,
    CB_VOICE_CONFIRM_PREFIX,
    agent_delete_confirm_keyboard,
    paginate_agent_slots,
    repo_list_keyboard,
    run_activity_keyboard,
    status_reply_markup,
)
from beachops.services.run_executor import (
    get_last_prompt,
    resolve_history_retry_mode,
    submit_user_prompt,
)
from beachops.services.ui_copy import (
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
    token_set,
    token_set_new_agent,
)

logger = logging.getLogger(__name__)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    app: AppContext = context.application.bot_data["app"]
    user = query.from_user
    data = query.data

    if data.startswith(CB_JOB_APPROVE_PREFIX):
        await _handle_job_action(
            query, app, user.id, data[len(CB_JOB_APPROVE_PREFIX) :], "approve"
        )
        return
    if data.startswith(CB_JOB_REJECT_PREFIX):
        await _handle_job_action(
            query, app, user.id, data[len(CB_JOB_REJECT_PREFIX) :], "reject"
        )
        return
    if data.startswith(CB_JOB_REVISION_PREFIX):
        await _handle_job_action(
            query, app, user.id, data[len(CB_JOB_REVISION_PREFIX) :], "revision"
        )
        return
    if data.startswith(CB_ROLLBACK_PREFIX):
        await _handle_rollback(
            query, app, user.id, data[len(CB_ROLLBACK_PREFIX) :]
        )
        return
    if data.startswith(CB_VOICE_CONFIRM_PREFIX):
        await _handle_voice_draft(
            query,
            context,
            app,
            user.id,
            data[len(CB_VOICE_CONFIRM_PREFIX) :],
            confirm=True,
        )
        return
    if data.startswith(CB_VOICE_CANCEL_PREFIX):
        await _handle_voice_draft(
            query,
            context,
            app,
            user.id,
            data[len(CB_VOICE_CANCEL_PREFIX) :],
            confirm=False,
        )
        return

    if data == CB_CANCEL:
        await _handle_cancel(query, context, app, user.id)
        return

    if data == CB_NAV_REPO:
        await _show_repo_list(query, app, user.id)
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
        assert query.message is not None
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass
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

    if data.startswith(CB_TOKEN_PREFIX):
        await _handle_token_select(query, app, user.id, data[len(CB_TOKEN_PREFIX) :])
        return

    if data.startswith(CB_RETRY_PREFIX):
        history_id = data[len(CB_RETRY_PREFIX) :]
        await _handle_retry(query, context, app, user.id, history_id)
        return

    if data == CB_RETRY_LAST:
        await _handle_retry_last(query, context, app, user.id)
        return

    if data == CB_BUILD_PLAN:
        await _handle_build_plan(query, context, app, user.id)
        return

    await query.answer()


async def _handle_voice_draft(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
    draft_id: str,
    *,
    confirm: bool,
) -> None:
    key = f"beachops:voice-draft:{user_id}:{draft_id}"
    encrypted = await app.redis.getdel(key)
    if encrypted is None:
        await query.answer("Расшифровка истекла или уже использована.", show_alert=True)
        return
    if not confirm:
        await query.answer("Отменено")
    else:
        payload = app.payload_crypto.decrypt_json(
            encrypted.decode("utf-8") if isinstance(encrypted, bytes) else encrypted
        )
        try:
            mode = UserMode(str(payload["mode"]))
            text = str(payload["text"])
        except (KeyError, ValueError):
            await query.answer("Черновик повреждён.", show_alert=True)
            return
        await query.answer("Отправлено")
        await submit_user_prompt(
            context=context,
            user_id=user_id,
            prompt=text,
            mode=mode,
            idempotency_key=f"voice:{user_id}:{draft_id}",
        )
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass


async def _handle_job_action(
    query,
    app: AppContext,
    user_id: int,
    token: str,
    action: str,
) -> None:
    if app.settings.role_for(user_id) != Role.OWNER:
        await query.answer("Только владелец может принять решение.", show_alert=True)
        return
    rate = await app.rate_limiter.check(
        subject=str(user_id),
        action="approval_callback",
        limit=app.settings.callback_rate_limit,
        window_sec=app.settings.callback_rate_window_sec,
    )
    if not rate.allowed:
        await query.answer(
            f"Слишком часто. Повторите через {rate.retry_after_sec} сек.",
            show_alert=True,
        )
        return
    job_id = await app.callback_tokens.consume_opaque(
        token,
        actor_id=user_id,
        action=action,
    )
    if job_id is None:
        await query.answer("Кнопка устарела или уже использована.", show_alert=True)
        return
    job = await app.jobs.get_internal(job_id)
    if job is None:
        await query.answer("Задача не найдена.", show_alert=True)
        return
    approval_kind = (
        ApprovalKind.PLAN_EXECUTION
        if job.status == JobStatus.AWAITING_APPROVAL
        else ApprovalKind.RESULT_REVIEW
    )
    approval = await app.approvals.get_for_job(
        job.actor_id,
        job.id,
        kind=approval_kind,
    )
    if approval is None:
        await query.answer("Подтверждение не найдено.", show_alert=True)
        return

    if action == "approve":
        decision = ApprovalDecision.APPROVED
        reason = None
    else:
        decision = ApprovalDecision.REJECTED
        reason = "revision requested" if action == "revision" else None
    decided = await app.approvals.decide(
        job.actor_id,
        approval.id,
        decided_by=user_id,
        decider_role=Role.OWNER,
        decision=decision,
        reason=reason,
    )
    if decided is None:
        await query.answer("Подтверждение истекло или уже использовано.", show_alert=True)
        return

    if action == "approve":
        try:
            result = await approve_job(app, job, approval_kind)
        except PermissionError as exc:
            await query.answer(str(exc), show_alert=True)
            return
        toast = "Одобрено" if result["status"] == "approved" else "Результат принят"
    elif action == "revision":
        await request_revision(
            app,
            job,
            "Перепроверь результат, исправь замечания и сохрани исходный scope.",
        )
        toast = "Доработка запрошена"
    else:
        await reject_job(app, job)
        toast = "Отклонено"

    await query.answer(toast)
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass


async def _handle_rollback(
    query,
    app: AppContext,
    user_id: int,
    token: str,
) -> None:
    from beachops.bot.handlers.rollback import load_rollback_target
    from beachops.services.deploy_trigger import DeployTriggerError, trigger_prod_deploy
    from beachops.services.ui_copy import rollback_failed, rollback_started

    if app.settings.role_for(user_id) != Role.OWNER:
        await query.answer("Только владелец может откатить прод.", show_alert=True)
        return
    job_id = await app.callback_tokens.consume_opaque(
        token,
        actor_id=user_id,
        action="rollback",
    )
    if job_id is None:
        await query.answer("Подтверждение устарело.", show_alert=True)
        return
    target = await load_rollback_target(app, job_id)
    if not target:
        await query.answer("Цель отката истекла. Повторите /rollback.", show_alert=True)
        return
    try:
        result = await trigger_prod_deploy(
            token=app.settings.github_token,
            repository=app.settings.github_repo,
            sha=target,
            workflow=app.settings.github_deploy_workflow,
            ref=app.settings.github_deploy_ref,
        )
    except DeployTriggerError as exc:
        await app.audit.append(
            actor_id=user_id,
            job_id=job_id,
            event_type="deploy.rollback",
            action="workflow_dispatch",
            outcome="failure",
            details={"sha": target, "error": str(exc)},
        )
        await query.answer(rollback_failed(str(exc))[:180], show_alert=True)
        return

    await app.deploy_history.record(
        sha=result.sha,
        ref=result.ref,
        reason="rollback",
    )
    job = await app.jobs.get(user_id, job_id)
    if job is not None:
        await app.jobs.transition(
            user_id,
            job_id,
            from_statuses=[JobStatus.DRAFT],
            to_status=JobStatus.SUCCEEDED,
            event_type="deploy.rollback",
        )
    await app.audit.append(
        actor_id=user_id,
        job_id=job_id,
        event_type="deploy.rollback",
        action="workflow_dispatch",
        outcome="success",
        details={"sha": result.sha, "ref": result.ref},
    )
    await query.answer("Откат запущен.", show_alert=True)
    if query.message:
        try:
            await query.message.edit_text(rollback_started(result.sha))
        except BadRequest:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except BadRequest:
                pass


async def _handle_cancel(query, context, app: AppContext, user_id: int) -> None:
    slot = await app.agent_slots.get_active(user_id)
    pending = app.job_queue.pending_count(user_id)
    forward_count = get_forward_context_buffer(context).item_count(user_id)
    coalesce_pending = get_prompt_coalesce(context).has_pending(user_id)
    if (
        not (slot and slot.active_run_id)
        and not app.job_queue.is_active(user_id)
        and pending == 0
        and forward_count == 0
        and not coalesce_pending
    ):
        await query.answer(cancel_none(), show_alert=True)
        return

    await query.answer(cancel_inline_answer())
    cleared_forward = await clear_forward_context(context, user_id)
    cleared_coalesce = await clear_prompt_coalesce(context, user_id)
    outcome = await cancel_user_work(app, user_id, bot=context.bot)

    if cancel_was_successful(
        outcome,
        cleared_forward=bool(cleared_forward),
        cleared_coalesce=bool(cleared_coalesce),
    ):
        is_admin = app.settings.is_admin(user_id)
        current = await app.users.get_mode(user_id)
        model_key = await app.users.get_cursor_model_key(
            user_id, default=app.settings.cursor_model
        )
        token_key, available_tokens = await token_ui_pair(app, user_id)
        repos = await app.repos.list_repos(user_id)
        try:
            await query.message.edit_reply_markup(
                reply_markup=status_reply_markup(
                    is_admin=is_admin,
                    current=current,
                    current_model_key=model_key,
                    has_repos=bool(repos),
                    current_token_key=token_key,
                    available_token_keys=available_tokens,
                ),
            )
        except BadRequest:
            pass
        await query.message.reply_text(
            cancel_ok(
                cleared_queue=outcome.cleared_queue,
                cleared_forwards=cleared_forward,
                cleared_coalesce=bool(cleared_coalesce),
            ),
        )
    else:
        await query.message.reply_text(cancel_failed())


async def _show_repo_list(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    assert query.message is not None
    repos = await app.repos.list_repos(user_id)
    if not repos:
        await edit_or_reply(
            query.message,
            text=repo_empty(app.settings.default_branch),
        )
        return

    lines = [repo_list_header(), ""]
    lines.extend(repo_list_line(r) for r in repos)
    await edit_or_reply(
        query.message,
        text="\n".join(lines),
        reply_markup=repo_list_keyboard(repos),
    )


async def _show_memory(query, app: AppContext, user_id: int) -> None:
    await query.answer()
    assert query.message is not None
    body, markup = await build_memory_list(app, user_id)
    if body is None:
        await edit_or_reply(query.message, text=memory_empty())
        return
    await edit_or_reply(query.message, text=body, reply_markup=markup)


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
    await app.agent_slots.ensure_default_slot(user_id)
    slots = await app.agent_slots.list_slots(user_id)
    await edit_or_reply(
        query.message,
        text=build_agent_list_text(slots),
        reply_markup=build_agent_list_markup(app, slots),
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
    if peek_pending(context) == slot_id:
        clear_pending(context)

    from beachops.services.agent_lifecycle import delete_agent_slot

    try:
        new_active = await delete_agent_slot(app, user_id, slot_id)
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


def _current_agent_list_page(query) -> int:
    """Best-effort page index from the "· n / m ·" nav button on the source message."""
    markup = query.message.reply_markup if query.message else None
    if markup is None:
        return 0
    for row in markup.inline_keyboard:
        for button in row:
            match = re.match(r"·\s*(\d+)\s*/\s*\d+\s*·", button.text or "")
            if match:
                return int(match.group(1)) - 1
    return 0


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
    assert query.message is not None
    page = _current_agent_list_page(query)
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
    await query.message.reply_text(agent_switched(slot.label))


async def _handle_agent_new(query, app: AppContext, user_id: int) -> None:
    try:
        slot = await app.agent_slots.create_new_slot(user_id)
    except AgentSlotsFullError:
        await query.answer(agent_slots_full(app.agent_slots.max_slots), show_alert=True)
        return

    await query.answer(f"Агент · {slot.label}")
    is_admin = app.settings.is_admin(user_id)
    mode = await app.users.get_mode(user_id)
    model_key = await app.users.get_cursor_model_key(
        user_id, default=app.settings.cursor_model
    )
    token_key, available_tokens = await token_ui_pair(app, user_id)
    repos = await app.repos.list_repos(user_id)
    await query.message.reply_text(
        agent_created(slot.label),
        reply_markup=status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_key,
            available_token_keys=available_tokens,
        ),
    )


async def _handle_mode_select(query, app: AppContext, user_id: int, mode_value: str) -> None:
    try:
        mode = UserMode(mode_value)
    except ValueError:
        await query.answer("Неизвестный режим", show_alert=True)
        return

    if not app.settings.can_use_mode(user_id, mode):
        from beachops.services.ui_copy import access_denied_mode

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

    token_key, available_tokens = await token_ui_pair(app, user_id)
    if active_run and active_run.message_id == query.message.message_id:
        markup = run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            current_token_key=token_key,
        )
    else:
        repos = await app.repos.list_repos(user_id)
        markup = status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_key,
            available_token_keys=available_tokens,
        )
    await query.message.edit_reply_markup(reply_markup=markup)


async def _handle_model_select(query, app: AppContext, user_id: int, model_value: str) -> None:
    from beachops.services.cursor_model_catalog import CursorModelCatalog

    model_key = normalize_cursor_model_key(
        model_value, default=app.settings.cursor_model
    )
    known = {item.value for item in CursorModelKey}
    if model_key.startswith("h:"):
        token_key = await app.users.get_cursor_token_key(user_id)
        resolved = await CursorModelCatalog(app).resolve_fingerprint(
            token_key, model_key[2:]
        )
        if not resolved:
            await query.answer("Модель недоступна, обновите /status", show_alert=True)
            return
        # Keep fingerprint as stored UI key so keyboards stay short.
        await app.users.set_cursor_model_key(user_id, model_key)
    elif model_key in known or model_key.startswith("dyn:"):
        await app.users.set_cursor_model_key(user_id, model_key)
    else:
        await query.answer("Неизвестная модель", show_alert=True)
        return

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

    token_key, available_tokens = await token_ui_pair(app, user_id)
    if active_run and active_run.message_id == query.message.message_id:
        markup = run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            current_token_key=token_key,
        )
    else:
        repos = await app.repos.list_repos(user_id)
        markup = status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_key,
            available_token_keys=available_tokens,
        )
    await query.message.edit_reply_markup(reply_markup=markup)


async def _handle_token_select(query, app: AppContext, user_id: int, token_value: str) -> None:
    if token_value not in {item.value for item in CursorTokenKey}:
        await query.answer("Неизвестный токен", show_alert=True)
        return
    if not app.settings.has_cursor_token(token_value):
        await query.answer("Токен не настроен на сервере", show_alert=True)
        return

    await app.users.set_cursor_token_key(user_id, token_value)
    is_admin = app.settings.is_admin(user_id)
    mode = await app.users.get_mode(user_id)
    model_key = await app.users.get_cursor_model_key(
        user_id, default=app.settings.cursor_model
    )
    slot = await app.agent_slots.get_active(user_id)
    active_run = app.active_runs.get(user_id)

    # Токен фиксируется на агенте при первом run — для уже созданного агента
    # переключение сработает только после /new.
    slot_pinned_other = bool(
        slot
        and slot.cursor_agent_id
        and normalize_cursor_token_key(slot.cursor_token_key) != token_value
    )
    toast = token_set_new_agent(token_value) if slot_pinned_other else token_set(token_value)
    await query.answer(toast, show_alert=slot_pinned_other)

    if active_run and active_run.message_id == query.message.message_id:
        markup = run_activity_keyboard(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            current_token_key=token_value,
        )
    else:
        repos = await app.repos.list_repos(user_id)
        available_tokens = available_token_keys_for_ui(app.settings)
        markup = status_reply_markup(
            is_admin=is_admin,
            current=mode,
            current_model_key=model_key,
            has_repos=bool(repos),
            current_token_key=token_value,
            available_token_keys=available_tokens,
        )
    try:
        await query.message.edit_reply_markup(reply_markup=markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


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


async def _handle_build_plan(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    app: AppContext,
    user_id: int,
) -> None:
    """Legacy static button cannot satisfy one-time approval requirements."""
    await query.answer(
        "Эта кнопка устарела. Откройте /approvals или Mini App.",
        show_alert=True,
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
