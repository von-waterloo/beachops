"""Reconcile BeachOps agent slots with Cursor Cloud Agents inventory."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from beachops.app_context import AppContext
from beachops.services.cursor_cloud_client import CursorCloudError
from beachops.services.cursor_token_ui import configured_cursor_token_keys

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DriftNote:
    slot_id: int
    cursor_agent_id: str | None
    detail: str


class AgentCloudReconciler:
    """Read-only sync for linked slots. Never auto-deletes cloud agents."""

    def __init__(self, app: AppContext) -> None:
        self._app = app

    async def sync_linked_slots(self, *, limit_per_token: int = 100) -> list[DriftNote]:
        notes: list[DriftNote] = []
        token_keys = configured_cursor_token_keys(self._app.settings)
        remote_by_key: dict[str, set[str]] = {}
        for token_key in token_keys:
            api_key = self._app.settings.cursor_api_key_for(token_key)
            try:
                agents = await self._app.cursor.list_agents(
                    api_key=api_key, limit=limit_per_token, include_archived=True
                )
            except CursorCloudError:
                logger.warning("list_agents failed for token %s", token_key, exc_info=True)
                continue
            remote_by_key[token_key] = {
                str(item.get("id") or "") for item in agents if item.get("id")
            }

        recent = await self._app.jobs.list_all_internal(limit=200)
        user_ids = sorted({job.actor_id for job in recent})
        for user_id in user_ids:
            slots = await self._app.agent_slots.list_slots(user_id)
            for slot in slots:
                if not slot.cursor_agent_id:
                    continue
                token_key = slot.cursor_token_key or "mt"
                remote = remote_by_key.get(token_key)
                if remote is None:
                    continue
                if slot.cursor_agent_id not in remote:
                    api_key = self._app.settings.cursor_api_key_for(token_key)
                    try:
                        await self._app.cursor.get_agent(
                            slot.cursor_agent_id, api_key=api_key
                        )
                        await self._app.agent_slots.set_cloud_status(
                            slot.id, cloud_status="active"
                        )
                    except CursorCloudError as exc:
                        if exc.status_code == 404:
                            await self._app.agent_slots.clear_cursor_agent(slot.id)
                            notes.append(
                                DriftNote(
                                    slot.id,
                                    slot.cursor_agent_id,
                                    "not_found_cleared_local_binding",
                                )
                            )
                        else:
                            await self._app.agent_slots.set_cloud_status(
                                slot.id, cloud_status="unknown"
                            )
                            notes.append(
                                DriftNote(
                                    slot.id,
                                    slot.cursor_agent_id,
                                    f"get_failed:{exc.status_code}",
                                )
                            )
                else:
                    await self._app.agent_slots.set_cloud_status(
                        slot.id, cloud_status="active"
                    )
        return notes

    async def audit_orphans(self, *, token_key: str = "mt") -> list[str]:
        """Return remote agent IDs not linked to any local slot (report only)."""
        api_key = self._app.settings.cursor_api_key_for(token_key)
        agents = await self._app.cursor.list_agents(api_key=api_key, limit=100)
        linked: set[str] = set()
        recent = await self._app.jobs.list_all_internal(limit=500)
        for job in recent:
            slots = await self._app.agent_slots.list_slots(job.actor_id)
            for slot in slots:
                if slot.cursor_agent_id:
                    linked.add(slot.cursor_agent_id)
        return [
            str(item.get("id"))
            for item in agents
            if item.get("id") and str(item["id"]) not in linked
        ]
