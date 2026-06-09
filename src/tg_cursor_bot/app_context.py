"""Shared application context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

from tg_cursor_bot.config.settings import Settings
from tg_cursor_bot.db.connection import check_postgres, create_pool
from tg_cursor_bot.db.repositories.agent_slots import AgentSlotRepository
from tg_cursor_bot.db.repositories.memory import MemoryRepository
from tg_cursor_bot.db.repositories.repos import RepoRepository
from tg_cursor_bot.db.repositories.users import UserRepository
from tg_cursor_bot.domain.active_run import ActiveRunInfo
from tg_cursor_bot.services.agent_slots import AgentSlotService
from tg_cursor_bot.services.cursor_agent import CursorAgentService
from tg_cursor_bot.services.embedding_service import EmbeddingService
from tg_cursor_bot.services.job_queue import JobQueue
from tg_cursor_bot.services.memory_service import MemoryService
from tg_cursor_bot.services.transcription import TranscriptionService


@dataclass
class AppContext:
    settings: Settings
    pool: asyncpg.Pool
    users: UserRepository
    repos: RepoRepository
    agent_slots: AgentSlotService
    memory: MemoryService
    cursor: CursorAgentService
    transcription: TranscriptionService
    job_queue: JobQueue
    workspace: Path
    active_runs: dict[int, ActiveRunInfo] = field(default_factory=dict)
    last_prompts: dict[int, tuple[str, float]] = field(default_factory=dict)

    @classmethod
    async def create(cls, settings: Settings) -> AppContext:
        pool = await create_pool(settings.database_url)
        await check_postgres(pool)

        workspace = settings.workspace_path
        workspace.mkdir(parents=True, exist_ok=True)

        memory_repo = MemoryRepository(pool)
        embeddings = EmbeddingService(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        )
        memory = MemoryService(memory_repo, embeddings, settings)

        repos = RepoRepository(pool)
        slot_repo = AgentSlotRepository(pool)

        return cls(
            settings=settings,
            pool=pool,
            users=UserRepository(pool),
            repos=repos,
            agent_slots=AgentSlotService(slot_repo, repos, settings),
            memory=memory,
            cursor=CursorAgentService(
                api_key=settings.cursor_api_key,
                model=settings.cursor_model,
                workspace=workspace,
            ),
            transcription=TranscriptionService(
                api_key=settings.openai_api_key,
                model=settings.transcribe_model,
            ),
            job_queue=JobQueue(max_queue_depth=settings.job_queue_depth),
            workspace=workspace,
        )

    async def close(self) -> None:
        await self.pool.close()
