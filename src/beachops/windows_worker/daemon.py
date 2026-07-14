"""Outbound Windows worker daemon (claim → local Cursor run → events)."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from cursor_sdk import AsyncClient

from beachops.domain.models import RepoConfig, UserMode
from beachops.domain.runtime import AgentRuntime
from beachops.services.cursor_agent import CursorAgentService
from beachops.services.stream_bridge import StreamState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SEC = 20.0
CLAIM_IDLE_SEC = 3.0
EVENT_THROTTLE_SEC = 1.0


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class BeachOpsWorkerClient:
    def __init__(
        self,
        *,
        api_url: str,
        token: str,
        hostname: str,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._token = token
        self._hostname = hostname
        self._http = httpx.AsyncClient(
            base_url=self._api_url,
            timeout=60.0,
            headers={"Authorization": f"Bearer {token}"},
        )

    def set_token(self, token: str) -> None:
        """Switch from bootstrap token to per-node token after register."""
        self._token = token
        self._http.headers["Authorization"] = f"Bearer {token}"

    @property
    def token(self) -> str:
        return self._token

    async def aclose(self) -> None:
        await self._http.aclose()

    async def register(self, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            "/api/workers/register",
            json={
                "hostname": self._hostname,
                "platform": "windows",
                "capabilities": dict(capabilities),
            },
        )
        response.raise_for_status()
        payload = response.json()
        node_token = str(payload.get("token") or "").strip()
        if not node_token:
            raise RuntimeError("register response missing node token")
        self.set_token(node_token)
        return payload

    async def heartbeat(self, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            "/api/workers/heartbeat",
            json={
                "hostname": self._hostname,
                "platform": "windows",
                "capabilities": dict(capabilities),
            },
        )
        response.raise_for_status()
        return response.json()

    async def claim(self) -> dict[str, Any] | None:
        response = await self._http.post("/api/workers/claim", json={})
        response.raise_for_status()
        payload = response.json()
        job = payload.get("job")
        return job if isinstance(job, dict) else None

    async def post_event(
        self,
        job_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        sequence: int = 0,
        idempotency_key: str | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "eventType": event_type,
            "sequence": sequence,
            "payload": dict(payload),
        }
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        response = await self._http.post(
            f"/api/workers/runs/{job_id}/events",
            json=body,
        )
        response.raise_for_status()


async def discover_local_agents(
    *,
    cwd: str | None,
    api_key: str,
    workspace: Path,
) -> dict[str, Any]:
    """Best-effort IDE local-agent discovery via cursor-sdk."""
    try:
        async with await AsyncClient.launch_bridge(workspace=str(workspace)) as client:
            result = await client.agents.list(
                runtime="local",
                cwd=cwd or str(workspace),
                api_key=api_key,
                limit=20,
            )
            agents = []
            for item in getattr(result, "items", None) or []:
                agents.append(
                    {
                        "id": getattr(item, "id", None) or getattr(item, "agent_id", None),
                        "name": getattr(item, "name", None),
                        "status": str(getattr(item, "status", "") or ""),
                    }
                )
            return {
                "localAgentsAvailable": True,
                "localAgents": agents,
                "localAgentCount": len(agents),
            }
    except Exception as exc:
        logger.warning("Local agent discovery failed: %s", exc)
        return {
            "localAgentsAvailable": False,
            "localAgents": [],
            "localAgentCount": 0,
            "localAgentsError": str(exc)[:300],
        }


async def execute_claimed_job(
    client: BeachOpsWorkerClient,
    job: Mapping[str, Any],
    *,
    cursor: CursorAgentService,
    api_key: str,
) -> None:
    job_id = str(job["id"])
    prompt = str(job.get("prompt") or "")
    mode = UserMode(str(job.get("mode") or "ask"))
    local_path = str(job.get("localPath") or "").strip()
    if not local_path:
        await client.post_event(
            job_id,
            event_type="run.failed",
            payload={"error": "localPath is required for Windows jobs"},
            idempotency_key=f"{job_id}:failed:no-path",
        )
        return

    repo = RepoConfig(
        id=int(job.get("repoId") or 0),
        tg_user_id=int(job.get("actorId") or 0),
        alias=str(job.get("repositoryAlias") or "local"),
        github_url=str(job.get("repositoryUrl") or "https://github.com/local/repo"),
        default_branch=str(job.get("branch") or "dev"),
        is_active=True,
    )
    model_key = str(job.get("modelKey") or job.get("model") or cursor._model)
    from beachops.domain.cursor_models import resolve_cursor_model

    model = resolve_cursor_model(model_key)
    memory_block = job.get("memoryBlock")
    if memory_block is not None:
        memory_block = str(memory_block) or None
    cursor_agent_id = job.get("cursorAgentId")
    if cursor_agent_id is not None:
        cursor_agent_id = str(cursor_agent_id)

    sequence = 0
    last_sent = 0.0

    async def on_update(state: StreamState) -> None:
        nonlocal sequence, last_sent
        now = asyncio.get_running_loop().time()
        if now - last_sent < EVENT_THROTTLE_SEC and state.status not in {
            "finished",
            "error",
            "cancelled",
        }:
            return
        last_sent = now
        sequence += 1
        await client.post_event(
            job_id,
            event_type="run.progress",
            sequence=sequence,
            payload={
                "status": state.status,
                "assistantText": (state.assistant_text or "")[:2000],
                "finalText": (state.final_text or "")[:2000],
                "agentId": state.agent_id,
                "runId": state.run_id,
                "prUrl": state.pr_url,
                "totalTokens": state.total_tokens,
            },
            idempotency_key=f"{job_id}:progress:{sequence}",
        )

    await client.post_event(
        job_id,
        event_type="run.started",
        payload={"localPath": local_path, "mode": mode.value, "modelKey": model_key},
        idempotency_key=f"{job_id}:started",
    )
    logger.info(
        "Windows run starting model=%s memory=%s",
        model_key,
        bool(memory_block),
        extra={"job_id": job_id, "action": "windows_run"},
    )

    from beachops.services.telegram_images import WebImageError, decode_payload_images

    try:
        images = decode_payload_images(job.get("images"))
    except WebImageError as exc:
        logger.error("Invalid images payload: %s", exc, extra={"job_id": job_id})
        await client.post_event(
            job_id,
            event_type="run.failed",
            payload={"status": "error", "error": "invalid images payload"},
            idempotency_key=f"{job_id}:run.failed",
        )
        return

    outcome, new_agent_id = await cursor.run_prompt(
        prompt=prompt,
        mode=mode,
        repo=repo,
        model=model,
        cursor_agent_id=cursor_agent_id,
        on_update=on_update,
        api_key=api_key,
        runtime=AgentRuntime.WINDOWS,
        local_path=local_path,
        memory_block=memory_block,
        images=images or None,
    )

    terminal = "run.failed" if outcome.status == "error" else "run.finished"
    await client.post_event(
        job_id,
        event_type=terminal,
        payload={
            "status": outcome.status,
            "error": outcome.error_message,
            "agentId": new_agent_id or outcome.state.agent_id,
            "runId": outcome.state.run_id,
            "finalText": (outcome.state.final_text or "")[:4000],
            "prUrl": outcome.state.pr_url,
            "totalTokens": outcome.state.total_tokens,
        },
        idempotency_key=f"{job_id}:{terminal}",
    )


async def run_daemon() -> None:
    api_url = _env("BEACHOPS_API_URL")
    token = _env("BEACHOPS_WORKER_TOKEN")
    hostname = _env("BEACHOPS_WORKER_HOSTNAME") or socket.gethostname()
    api_key = _env("CURSOR_API_KEY")
    model = _env("CURSOR_MODEL") or "composer-2.5"
    workspace = Path(_env("WORKSPACE_PATH") or "./data/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    if not api_url or not token:
        raise SystemExit(
            "BEACHOPS_API_URL and BEACHOPS_WORKER_TOKEN are required"
        )
    if not api_key:
        raise SystemExit("CURSOR_API_KEY is required on the Windows worker")

    token_path = Path(
        _env("BEACHOPS_WORKER_TOKEN_FILE")
        or str(workspace / ".beachops-worker-node-token")
    )
    client = BeachOpsWorkerClient(api_url=api_url, token=token, hostname=hostname)
    cursor = CursorAgentService(api_key=api_key, model=model, workspace=workspace)
    discovery_cwd = _env("BEACHOPS_LOCAL_CWD") or str(workspace)
    enrolled = False

    saved = ""
    if token_path.is_file():
        saved = token_path.read_text(encoding="utf-8").strip()
        if saved:
            client.set_token(saved)
            enrolled = True

    logger.info("Windows worker starting hostname=%s api=%s", hostname, api_url)
    try:
        while True:
            capabilities = {
                "runtime": "windows",
                "hostname": hostname,
                "cwd": discovery_cwd,
            }
            capabilities.update(
                await discover_local_agents(
                    cwd=discovery_cwd,
                    api_key=api_key,
                    workspace=workspace,
                )
            )
            try:
                if not enrolled:
                    registered = await client.register(capabilities)
                    token_path.parent.mkdir(parents=True, exist_ok=True)
                    token_path.write_text(client.token, encoding="utf-8")
                    enrolled = True
                    logger.info(
                        "Registered worker node_id=%s",
                        registered.get("id"),
                    )
                await client.heartbeat(capabilities)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401 and enrolled:
                    logger.warning("Node token rejected; re-registering")
                    enrolled = False
                    client.set_token(token)
                    await asyncio.sleep(1.0)
                    continue
                logger.exception("Heartbeat failed")
                await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
                continue
            except Exception:
                logger.exception("Heartbeat failed")
                await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
                continue

            try:
                job = await client.claim()
            except Exception:
                logger.exception("Claim failed")
                await asyncio.sleep(CLAIM_IDLE_SEC)
                continue

            if job is None:
                await asyncio.sleep(CLAIM_IDLE_SEC)
                continue

            logger.info("Claimed job %s", job.get("id"))
            try:
                await execute_claimed_job(
                    client,
                    job,
                    cursor=cursor,
                    api_key=api_key,
                )
            except Exception as exc:
                logger.exception("Job execution failed")
                try:
                    await client.post_event(
                        str(job["id"]),
                        event_type="run.failed",
                        payload={"error": str(exc)[:1000]},
                        idempotency_key=f"{job['id']}:failed:exception",
                    )
                except Exception:
                    logger.exception("Failed to report job failure")
    finally:
        await client.aclose()
