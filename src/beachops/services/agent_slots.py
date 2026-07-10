"""Agent slot orchestration (multi-session Cursor agents)."""

from __future__ import annotations

from dataclasses import dataclass

from beachops.config.settings import Settings
from beachops.db.repositories.agent_slots import AgentSlotRepository
from beachops.db.repositories.repos import RepoRepository
from beachops.domain.models import AgentSlot, RepoConfig
from beachops.services.agent_slot_naming import (
    is_auto_slot_label,
    label_from_prompt,
    random_slot_label,
)


class AgentSlotsFullError(Exception):
    """User reached AGENT_SLOTS_MAX."""


class AgentSlotLastError(Exception):
    """Cannot delete the only remaining agent slot."""


@dataclass(frozen=True, slots=True)
class RunContext:
    slot: AgentSlot
    repo: RepoConfig


class AgentSlotService:
    def __init__(
        self,
        slots: AgentSlotRepository,
        repos: RepoRepository,
        settings: Settings,
    ) -> None:
        self._slots = slots
        self._repos = repos
        self._settings = settings

    @property
    def max_slots(self) -> int:
        return self._settings.agent_slots_max

    async def list_slots(self, tg_user_id: int) -> list[AgentSlot]:
        return await self._slots.list_slots(tg_user_id)

    async def get_active(self, tg_user_id: int) -> AgentSlot | None:
        return await self._slots.get_active(tg_user_id)

    async def ensure_default_slot(self, tg_user_id: int) -> AgentSlot:
        active = await self._slots.get_active(tg_user_id)
        if active is not None:
            return active

        slots = await self._slots.list_slots(tg_user_id)
        if slots:
            activated = await self.activate_slot(tg_user_id, slots[0].id)
            assert activated is not None
            return activated

        repo = await self._repos.resolve_active_repo(tg_user_id, self._settings)
        count = await self._slots.count_slots(tg_user_id)
        return await self._slots.create_slot(
            tg_user_id,
            label=random_slot_label(),
            repo_id=repo.id if repo else None,
            make_active=True,
        )

    async def activate_slot(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        slot = await self._slots.set_active(tg_user_id, slot_id)
        if slot is None:
            return None
        if slot.repo_id is not None:
            await self._repos.set_active_by_id(tg_user_id, slot.repo_id)
        return slot

    async def create_new_slot(self, tg_user_id: int) -> AgentSlot:
        count = await self._slots.count_slots(tg_user_id)
        if count >= self.max_slots:
            raise AgentSlotsFullError()

        repo = await self._repos.get_active_repo(tg_user_id)
        if repo is None:
            repo = await self._repos.resolve_active_repo(tg_user_id, self._settings)

        label = random_slot_label()
        return await self._slots.create_slot(
            tg_user_id,
            label=label,
            repo_id=repo.id if repo else None,
            make_active=True,
        )

    async def get_run_context(self, tg_user_id: int) -> RunContext | None:
        slot = await self.ensure_default_slot(tg_user_id)
        repo: RepoConfig | None = None
        if slot.repo_id is not None:
            repo = await self._repos.get_by_id(tg_user_id, slot.repo_id)
        if repo is None:
            repo = await self._repos.resolve_active_repo(tg_user_id, self._settings)
            if repo is not None and slot.cursor_agent_id is None:
                await self._slots.update_repo_id(slot.id, repo.id)
                slot = await self._slots.get_by_id(tg_user_id, slot.id) or slot
        if repo is None:
            return None
        return RunContext(slot=slot, repo=repo)

    async def sync_active_slot_repo(self, tg_user_id: int, repo: RepoConfig) -> None:
        """After manual repo switch: bind active slot to the new repo.

        Cursor agents are repo-scoped — if the slot already had an agent on
        another repo, clear it so the next run creates a fresh agent.
        """
        slot = await self.ensure_default_slot(tg_user_id)
        if slot.repo_id == repo.id:
            return
        await self._slots.rebind_repo(slot.id, repo.id)

    async def update_cursor_agent(
        self,
        slot_id: int,
        cursor_agent_id: str,
        *,
        token_key: str | None = None,
    ) -> None:
        await self._slots.update_cursor_agent(
            slot_id, cursor_agent_id, token_key=token_key
        )

    async def set_active_run(self, slot_id: int, run_id: str | None) -> None:
        await self._slots.set_active_run(slot_id, run_id)

    async def clear_stale_active_runs(self) -> None:
        await self._slots.clear_all_active_runs()

    async def get_slot(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        return await self._slots.get_by_id(tg_user_id, slot_id)

    async def rename_active(self, tg_user_id: int, label: str) -> AgentSlot | None:
        slot = await self.get_active(tg_user_id)
        if slot is None:
            return None
        return await self.rename_slot(tg_user_id, slot.id, label)

    async def rename_slot(
        self,
        tg_user_id: int,
        slot_id: int,
        label: str,
    ) -> AgentSlot | None:
        cleaned = label.strip()
        if not cleaned:
            return None
        if len(cleaned) > 64:
            cleaned = cleaned[:64].rstrip()
        if not await self._slots.update_label(tg_user_id, slot_id, cleaned):
            return None
        return await self._slots.get_by_id(tg_user_id, slot_id)

    async def maybe_autoname_active(self, tg_user_id: int, prompt: str) -> None:
        slot = await self.get_active(tg_user_id)
        if slot is None or not is_auto_slot_label(slot.label):
            return
        new_label = label_from_prompt(prompt)
        if not new_label:
            return
        await self._slots.update_label(tg_user_id, slot.id, new_label)

    async def update_runtime_config(
        self,
        tg_user_id: int,
        slot_id: int,
        *,
        runtime: str | None = None,
        local_path: str | None = None,
        clear_local_path: bool = False,
        preferred_worker_id: str | None = None,
        clear_preferred_worker: bool = False,
    ) -> AgentSlot | None:
        if runtime is not None and runtime not in {"cloud", "windows"}:
            raise ValueError("runtime must be cloud or windows")
        if runtime == "windows" and not clear_local_path:
            current = await self._slots.get_by_id(tg_user_id, slot_id)
            path = local_path if local_path is not None else (
                current.local_path if current else None
            )
            if not (path or "").strip():
                raise ValueError("local_path is required for Windows runtime")
        return await self._slots.update_runtime_config(
            tg_user_id,
            slot_id,
            runtime=runtime,
            local_path=local_path,
            clear_local_path=clear_local_path,
            preferred_worker_id=preferred_worker_id,
            clear_preferred_worker=clear_preferred_worker,
        )

    async def delete_slot(self, tg_user_id: int, slot_id: int) -> AgentSlot | None:
        slot = await self._slots.get_by_id(tg_user_id, slot_id)
        if slot is None:
            return None

        count = await self._slots.count_slots(tg_user_id)
        if count <= 1:
            raise AgentSlotLastError()

        new_active = await self._slots.delete_slot(tg_user_id, slot_id)
        if new_active is None:
            return None

        if new_active.is_active and new_active.repo_id is not None:
            await self._repos.set_active_by_id(tg_user_id, new_active.repo_id)
        return new_active
