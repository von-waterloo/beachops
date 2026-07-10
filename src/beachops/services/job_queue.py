"""Per-user job queue with one active worker and FIFO pending slots."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SubmitResult(str, Enum):
    STARTED = "started"
    QUEUED = "queued"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SubmitInfo:
    result: SubmitResult
    queue_position: int = 0


class RunCancelled(Exception):
    """Raised when a user cancels an in-flight job."""


class JobQueue:
    def __init__(self, max_queue_depth: int = 2) -> None:
        self._max_queue_depth = max_queue_depth
        self._pending: dict[int, deque[Callable[[], Awaitable[None]]]] = {}
        self._active: dict[int, bool] = {}
        self._cancel_requested: dict[int, bool] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _pending_for(self, user_id: int) -> deque[Callable[[], Awaitable[None]]]:
        if user_id not in self._pending:
            self._pending[user_id] = deque()
        return self._pending[user_id]

    async def submit(
        self,
        user_id: int,
        coro_factory: Callable[[], Awaitable[None]],
    ) -> SubmitInfo:
        async with self._lock_for(user_id):
            if not self._active.get(user_id) and not self._pending_for(user_id):
                self._active[user_id] = True
                asyncio.create_task(self._worker(user_id, coro_factory))
                return SubmitInfo(SubmitResult.STARTED)

            pending = self._pending_for(user_id)
            if len(pending) < self._max_queue_depth:
                pending.append(coro_factory)
                return SubmitInfo(SubmitResult.QUEUED, queue_position=len(pending))

            return SubmitInfo(SubmitResult.REJECTED)

    async def _worker(
        self,
        user_id: int,
        first: Callable[[], Awaitable[None]] | None,
    ) -> None:
        job = first
        try:
            while job is not None:
                try:
                    await job()
                except Exception:
                    logger.exception("Job failed for user %s", user_id)
                pending = self._pending_for(user_id)
                job = pending.popleft() if pending else None
        finally:
            self._active[user_id] = False

    def clear_pending(self, user_id: int) -> int:
        pending = self._pending_for(user_id)
        count = len(pending)
        pending.clear()
        return count

    def request_cancel(self, user_id: int) -> None:
        self._cancel_requested[user_id] = True

    def clear_cancel(self, user_id: int) -> None:
        self._cancel_requested.pop(user_id, None)

    def is_cancelled(self, user_id: int) -> bool:
        return self._cancel_requested.get(user_id, False)

    def pending_count(self, user_id: int) -> int:
        return len(self._pending_for(user_id))

    def is_active(self, user_id: int) -> bool:
        return self._active.get(user_id, False)

    def is_busy(self, user_id: int) -> bool:
        return self.is_active(user_id) or self.pending_count(user_id) > 0

    def has_active_workers(self) -> bool:
        return any(self._active.values())

    async def drain(self, timeout: float = 15.0) -> None:
        """Wait for in-flight jobs to finish (best-effort on shutdown)."""
        if not self.has_active_workers():
            return
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if not self.has_active_workers():
                return
            await asyncio.sleep(0.25)
        active_users = [uid for uid, busy in self._active.items() if busy]
        logger.warning(
            "Job queue drain timed out with active users: %s",
            active_users,
        )
