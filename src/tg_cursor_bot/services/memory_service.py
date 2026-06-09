"""Semantic memory: index runs/notes and recall for prompts."""

from __future__ import annotations

import logging

from tg_cursor_bot.config.settings import Settings
from tg_cursor_bot.db.repositories.memory import MemoryRepository
from tg_cursor_bot.domain.models import MemoryEntry, RunSummary
from tg_cursor_bot.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

MAX_RECALL_CHARS = 1500


class MemoryService:
    def __init__(
        self,
        repo: MemoryRepository,
        embeddings: EmbeddingService,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._embeddings = embeddings
        self._settings = settings

    async def index_run(
        self,
        *,
        tg_user_id: int,
        repo_id: int | None,
        prompt: str,
        result: str,
        mode: str,
        run_id: str | None,
        pr_url: str | None,
        status: str,
        duration_ms: int | None,
    ) -> None:
        title = prompt[:80] + ("…" if len(prompt) > 80 else "")
        body = result
        embed_text = f"{prompt}\n\n{result}"
        embedding = await self._embeddings.embed(
            embed_text,
            max_chars=self._settings.memory_embed_max_chars,
        )
        await self._repo.insert(
            tg_user_id=tg_user_id,
            repo_id=repo_id,
            kind="run",
            title=title,
            body=body,
            source_prompt=prompt,
            embedding=embedding,
            run_id=run_id,
            mode=mode,
            pr_url=pr_url,
            status=status,
            duration_ms=duration_ms,
        )

    async def add_note(
        self,
        *,
        tg_user_id: int,
        repo_id: int | None,
        text: str,
    ) -> int:
        title = text[:80] + ("…" if len(text) > 80 else "")
        embedding = await self._embeddings.embed(
            text,
            max_chars=self._settings.memory_embed_max_chars,
        )
        return await self._repo.insert(
            tg_user_id=tg_user_id,
            repo_id=repo_id,
            kind="note",
            title=title,
            body=text,
            embedding=embedding,
        )

    async def recall(
        self,
        tg_user_id: int,
        repo_id: int | None,
        query: str,
    ) -> list[MemoryEntry]:
        if not query.strip():
            return []

        embedding = await self._embeddings.embed(
            query,
            max_chars=self._settings.memory_embed_max_chars,
        )
        if embedding is None:
            logger.warning("Recall fallback to text search for user %s", tg_user_id)
            return await self._repo.search_text(
                tg_user_id,
                repo_id,
                query,
                limit=self._settings.memory_recall_k,
            )

        return await self._repo.recall(
            tg_user_id,
            repo_id,
            embedding,
            limit=self._settings.memory_recall_k,
        )

    async def list_recent(
        self,
        tg_user_id: int,
        *,
        repo_id: int | None = None,
    ) -> list[MemoryEntry]:
        return await self._repo.list_recent(
            tg_user_id,
            limit=self._settings.memory_list_limit,
            repo_id=repo_id,
        )

    async def search(
        self,
        tg_user_id: int,
        query: str,
        *,
        repo_id: int | None = None,
    ) -> list[MemoryEntry]:
        embedding = await self._embeddings.embed(
            query,
            max_chars=self._settings.memory_embed_max_chars,
        )
        if embedding is not None:
            return await self._repo.search_semantic(
                tg_user_id,
                repo_id,
                embedding,
                limit=self._settings.memory_list_limit,
            )
        return await self._repo.search_text(
            tg_user_id,
            repo_id,
            query,
            limit=self._settings.memory_list_limit,
        )

    async def get_by_id(self, tg_user_id: int, entry_id: int) -> MemoryEntry | None:
        return await self._repo.get_by_id(tg_user_id, entry_id)

    async def list_runs_for_retry(self, tg_user_id: int) -> list[RunSummary]:
        return await self._repo.list_runs_for_retry(
            tg_user_id,
            limit=self._settings.memory_list_limit,
        )

    async def get_run_by_id(self, tg_user_id: int, entry_id: int) -> RunSummary | None:
        return await self._repo.get_run_by_id(tg_user_id, entry_id)

    def format_recall_block(self, entries: list[MemoryEntry]) -> str:
        if not entries:
            return ""

        lines: list[str] = []
        total = 0
        for entry in entries:
            kind_label = "заметка" if entry.kind == "note" else "запуск"
            snippet = entry.body[:400] + ("…" if len(entry.body) > 400 else "")
            line = f"[{kind_label}] {entry.title}\n{snippet}"
            if total + len(line) > MAX_RECALL_CHARS:
                break
            lines.append(line)
            total += len(line) + 1

        return "\n\n".join(lines)
