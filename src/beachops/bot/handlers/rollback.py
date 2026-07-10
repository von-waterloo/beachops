"""Owner-only prod rollback to a previous deploy SHA."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from beachops.app_context import AppContext
from beachops.domain.security import JobKind, JobStatus, RiskLevel, Role
from beachops.services.inline_keyboards import rollback_keyboard
from beachops.services.ui_copy import (
    rollback_confirm,
    rollback_dispatch_disabled,
    rollback_need_sha,
    rollback_owner_only,
)

_ROLLBACK_TARGET_PREFIX = "beachops:rollback:target:"


async def rollback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    app: AppContext = context.application.bot_data["app"]
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return
    if app.settings.role_for(user.id) != Role.OWNER:
        await message.reply_text(rollback_owner_only())
        return
    if not app.settings.github_deploy_dispatch:
        await message.reply_text(rollback_dispatch_disabled())
        return
    if not app.settings.github_token.strip() or not app.settings.github_repo.strip():
        await message.reply_text(rollback_dispatch_disabled())
        return

    args = context.args or []
    explicit_sha = args[0].strip() if args else ""
    recent = await app.deploy_history.recent(limit=5)
    tip = recent[0].sha if recent else None
    target = explicit_sha or await app.deploy_history.previous_sha(current_hint=tip)
    if not target:
        await message.reply_text(rollback_need_sha())
        return

    confirmation = await app.jobs.create(
        user.id,
        kind=JobKind.DEPLOY,
        risk_level=RiskLevel.HIGH,
        status=JobStatus.DRAFT,
        summary=f"Rollback prod to {target[:12]}",
    )
    ttl = app.settings.callback_token_ttl_sec
    await app.redis.set(
        f"{_ROLLBACK_TARGET_PREFIX}{confirmation.id}",
        target.encode("utf-8"),
        ex=ttl,
    )
    token = await app.callback_tokens.issue(
        user.id,
        confirmation.id,
        action="rollback",
        ttl_sec=ttl,
    )
    await message.reply_text(
        rollback_confirm(target, recent_tip=tip),
        reply_markup=rollback_keyboard(token),
        parse_mode="Markdown",
    )


async def load_rollback_target(app: AppContext, job_id) -> str | None:
    raw = await app.redis.getdel(f"{_ROLLBACK_TARGET_PREFIX}{job_id}")
    if not raw:
        return None
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
