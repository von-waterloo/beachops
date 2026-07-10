"""Record successful prod deploys so owner can /rollback to a previous SHA."""

from __future__ import annotations

import json
from dataclasses import dataclass

from redis.asyncio import Redis

_HISTORY_KEY = "beachops:deploy:history"
_MAX_ENTRIES = 20


@dataclass(frozen=True)
class DeployRecord:
    sha: str
    ref: str
    reason: str  # "deploy" | "rollback"


class DeployHistory:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def record(self, *, sha: str, ref: str, reason: str = "deploy") -> None:
        digest = sha.strip()
        if not digest:
            return
        payload = json.dumps(
            {"sha": digest, "ref": ref.strip() or "main", "reason": reason},
            separators=(",", ":"),
        )
        await self._redis.lpush(_HISTORY_KEY, payload.encode("utf-8"))
        await self._redis.ltrim(_HISTORY_KEY, 0, _MAX_ENTRIES - 1)

    async def recent(self, *, limit: int = 10) -> list[DeployRecord]:
        raw_items = await self._redis.lrange(_HISTORY_KEY, 0, max(0, limit - 1))
        records: list[DeployRecord] = []
        for raw in raw_items:
            try:
                data = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            sha = str(data.get("sha") or "").strip()
            if not sha:
                continue
            records.append(
                DeployRecord(
                    sha=sha,
                    ref=str(data.get("ref") or "main"),
                    reason=str(data.get("reason") or "deploy"),
                )
            )
        return records

    async def previous_sha(self, *, current_hint: str | None = None) -> str | None:
        """Return the SHA to roll back to (skip identical tip if known)."""
        records = await self.recent(limit=_MAX_ENTRIES)
        if not records:
            return None
        tip = (current_hint or records[0].sha).strip()
        for record in records:
            if record.sha != tip:
                return record.sha
        return None
