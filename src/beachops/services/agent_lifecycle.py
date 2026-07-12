"""Agent slot delete / archive / unarchive with Cursor lifecycle safety."""

from __future__ import annotations

import logging

from beachops.app_context import AppContext
from beachops.domain.cursor_tokens import normalize_cursor_token_key
from beachops.domain.models import AgentSlot
from beachops.services.agent_slots import AgentSlotLastError
from beachops.services.cancel_service import cancel_user_work
from beachops.services.cursor_cloud_client import CursorCloudError

logger = logging.getLogger(__name__)


async def delete_agent_slot(
    app: AppContext,
    user_id: int,
    slot_id: int,
    *,
    cancel_if_active: bool = True,
) -> AgentSlot | None:
    """Cancel active work, archive remote Cursor agent, then delete local slot."""
    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None:
        return None

    active = await app.agent_slots.get_active(user_id)
    if (
        cancel_if_active
        and active is not None
        and active.id == slot_id
        and (
            active.active_run_id
            or app.job_queue.is_active(user_id)
            or app.job_queue.pending_count(user_id) > 0
        )
    ):
        await cancel_user_work(app, user_id)

    if slot.cursor_agent_id:
        token_key = normalize_cursor_token_key(slot.cursor_token_key)
        try:
            await app.cursor.archive_agent(
                slot.cursor_agent_id,
                api_key=app.settings.cursor_api_key_for(token_key),
            )
        except Exception:
            logger.warning(
                "archive before delete failed for %s",
                slot.cursor_agent_id,
                exc_info=True,
            )

    try:
        return await app.agent_slots.delete_slot(user_id, slot_id)
    except AgentSlotLastError:
        raise


async def archive_slot_agent(app: AppContext, user_id: int, slot_id: int) -> AgentSlot | None:
    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None or not slot.cursor_agent_id:
        return slot
    token_key = normalize_cursor_token_key(slot.cursor_token_key)
    await app.cursor.archive_agent(
        slot.cursor_agent_id,
        api_key=app.settings.cursor_api_key_for(token_key),
    )
    await app.agent_slots.set_cloud_status(slot_id, cloud_status="archived")
    return await app.agent_slots.get_slot(user_id, slot_id)


async def unarchive_slot_agent(
    app: AppContext, user_id: int, slot_id: int
) -> AgentSlot | None:
    slot = await app.agent_slots.get_slot(user_id, slot_id)
    if slot is None or not slot.cursor_agent_id:
        return slot
    token_key = normalize_cursor_token_key(slot.cursor_token_key)
    await app.cursor.unarchive_agent(
        slot.cursor_agent_id,
        api_key=app.settings.cursor_api_key_for(token_key),
    )
    await app.agent_slots.set_cloud_status(slot_id, cloud_status="active")
    return await app.agent_slots.get_slot(user_id, slot_id)


async def permanently_delete_remote_agent(
    app: AppContext,
    user_id: int,
    *,
    cursor_agent_id: str,
    token_key: str | None,
    require_unlinked: bool = True,
) -> None:
    """Irreversible DELETE. Caller must confirm twice at UI layer."""
    if require_unlinked:
        slots = await app.agent_slots.list_slots(user_id)
        if any(s.cursor_agent_id == cursor_agent_id for s in slots):
            raise CursorCloudError(
                "agent still linked to a BeachOps slot; unlink/archive first"
            )
    key = normalize_cursor_token_key(token_key)
    await app.cursor.delete_agent(
        cursor_agent_id,
        api_key=app.settings.cursor_api_key_for(key),
    )
