"""Cursor Cloud Agents API v1 HTTP client."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from beachops.services.cursor_sse import SseEvent, parse_sse_stream

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.cursor.com"


class CursorCloudError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class CursorAgentBusyError(CursorCloudError):
    pass


class CursorStreamExpiredError(CursorCloudError):
    pass


def is_stream_expired_message(message: str) -> bool:
    """True when Cursor closed the SSE replay window (410 / stale Last-Event-ID)."""
    lower = (message or "").lower()
    if not lower:
        return False
    if "stream_expired" in lower or "stream expired" in lower:
        return True
    return "stream" in lower and "no longer available" in lower


def is_agent_gone_error(exc: Exception) -> bool:
    """True when the Cursor agent/run no longer exists (queue must not wait forever)."""
    code = ""
    message = str(exc or "")
    status_code: int | None = None
    if isinstance(exc, CursorCloudError):
        code = (exc.code or "").lower()
        message = exc.message or message
        status_code = exc.status_code
    lower = message.lower()
    if code in {"agent_not_found", "not_found", "run_not_found"}:
        return True
    if "agent not found" in lower or "run not found" in lower:
        return True
    if status_code == 404 and "not found" in lower:
        return True
    return False


@dataclass(frozen=True, slots=True)
class PromptImage:
    data: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class ModelParam:
    id: str
    value: str


@dataclass(frozen=True, slots=True)
class ModelSelection:
    id: str
    params: tuple[ModelParam, ...] = ()

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id}
        if self.params:
            payload["params"] = [{"id": p.id, "value": p.value} for p in self.params]
        return payload


@dataclass(frozen=True, slots=True)
class AgentRef:
    id: str
    status: str | None = None
    url: str | None = None
    name: str | None = None
    latest_run_id: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunRef:
    id: str
    agent_id: str
    status: str
    result: str | None = None
    duration_ms: int | None = None
    git: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UsageBreakdown:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    path: str
    size_bytes: int | None = None
    updated_at: str | None = None


def _auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _usage_from_mapping(data: Mapping[str, Any] | None) -> UsageBreakdown:
    if not data:
        return UsageBreakdown()
    return UsageBreakdown(
        input_tokens=int(data.get("inputTokens") or data.get("input_tokens") or 0),
        output_tokens=int(data.get("outputTokens") or data.get("output_tokens") or 0),
        cache_read_tokens=int(
            data.get("cacheReadTokens") or data.get("cache_read_tokens") or 0
        ),
        cache_write_tokens=int(
            data.get("cacheWriteTokens") or data.get("cache_write_tokens") or 0
        ),
        total_tokens=int(data.get("totalTokens") or data.get("total_tokens") or 0),
    )


class CursorCloudClient:
    """Thin async client for https://api.cursor.com/v1/*."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_API_BASE,
        timeout_sec: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_sec, read=timeout_sec),
            headers={
                "Authorization": _auth_header(api_key),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> CursorCloudClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def with_api_key(self, api_key: str) -> CursorCloudClient:
        return CursorCloudClient(
            api_key=api_key,
            base_url=self._base_url,
            client=None,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        accept: str | None = None,
    ) -> httpx.Response:
        headers = {}
        if accept:
            headers["Accept"] = accept
        response = await self._client.request(
            method,
            path,
            json=dict(json_body) if json_body is not None else None,
            params=dict(params) if params is not None else None,
            headers=headers or None,
        )
        if response.status_code == 409:
            payload = _safe_json(response)
            code = str(payload.get("error") or payload.get("code") or "conflict")
            message = str(
                payload.get("message")
                or payload.get("error")
                or "Cursor agent is busy"
            )
            if "busy" in message.lower() or "busy" in code.lower():
                raise CursorAgentBusyError(
                    message, status_code=409, code=code
                )
            raise CursorCloudError(message, status_code=409, code=code)
        if response.status_code == 410:
            payload = _safe_json(response)
            raise CursorStreamExpiredError(
                str(payload.get("message") or "stream expired"),
                status_code=410,
                code=str(payload.get("code") or "stream_expired"),
            )
        if response.status_code >= 400:
            payload = _safe_json(response)
            message = str(
                payload.get("message")
                or payload.get("error")
                or response.text
                or f"HTTP {response.status_code}"
            )
            raise CursorCloudError(
                message,
                status_code=response.status_code,
                code=str(payload.get("code") or payload.get("error") or ""),
            )
        return response

    async def create_agent(
        self,
        *,
        prompt_text: str,
        repo_url: str,
        starting_ref: str,
        model: ModelSelection | str | None = None,
        mode: str = "agent",
        images: Sequence[PromptImage] | None = None,
        auto_create_pr: bool = False,
        work_on_current_branch: bool = False,
        skip_reviewer_request: bool = True,
        mcp_servers: Sequence[Mapping[str, Any]] | None = None,
        name: str | None = None,
    ) -> tuple[AgentRef, RunRef]:
        body: dict[str, Any] = {
            "prompt": _prompt_body(prompt_text, images),
            "repos": [{"url": repo_url, "startingRef": starting_ref}],
            "mode": mode,
            "autoCreatePR": auto_create_pr,
            "workOnCurrentBranch": work_on_current_branch,
            "skipReviewerRequest": skip_reviewer_request,
        }
        if name:
            body["name"] = name
        if model is not None:
            body["model"] = (
                model.to_api() if isinstance(model, ModelSelection) else {"id": model}
            )
        if mcp_servers:
            body["mcpServers"] = list(mcp_servers)
        response = await self._request("POST", "/v1/agents", json_body=body)
        payload = response.json()
        agent = _agent_from_payload(payload.get("agent") or payload)
        run = _run_from_payload(payload.get("run") or {}, default_agent_id=agent.id)
        return agent, run

    async def create_run(
        self,
        agent_id: str,
        *,
        prompt_text: str,
        mode: str | None = None,
        images: Sequence[PromptImage] | None = None,
        mcp_servers: Sequence[Mapping[str, Any]] | None = None,
    ) -> RunRef:
        body: dict[str, Any] = {"prompt": _prompt_body(prompt_text, images)}
        if mode:
            body["mode"] = mode
        if mcp_servers:
            body["mcpServers"] = list(mcp_servers)
        response = await self._request(
            "POST", f"/v1/agents/{agent_id}/runs", json_body=body
        )
        payload = response.json()
        run_payload = payload.get("run") or payload
        return _run_from_payload(run_payload, default_agent_id=agent_id)

    async def get_agent(self, agent_id: str) -> AgentRef:
        response = await self._request("GET", f"/v1/agents/{agent_id}")
        return _agent_from_payload(response.json())

    async def list_agents(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        pr_url: str | None = None,
        include_archived: bool = True,
    ) -> tuple[list[AgentRef], str | None]:
        params: dict[str, Any] = {
            "limit": max(1, min(limit, 100)),
            "includeArchived": str(include_archived).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        if pr_url:
            params["prUrl"] = pr_url
        response = await self._request("GET", "/v1/agents", params=params)
        payload = response.json()
        items = payload.get("items") or payload.get("agents") or []
        agents = [_agent_from_payload(item) for item in items if isinstance(item, dict)]
        next_cursor = payload.get("nextCursor")
        return agents, str(next_cursor) if next_cursor else None

    async def list_runs(
        self,
        agent_id: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[RunRef], str | None]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
        if cursor:
            params["cursor"] = cursor
        response = await self._request(
            "GET", f"/v1/agents/{agent_id}/runs", params=params
        )
        payload = response.json()
        items = payload.get("items") or []
        runs = [
            _run_from_payload(item, default_agent_id=agent_id)
            for item in items
            if isinstance(item, dict)
        ]
        next_cursor = payload.get("nextCursor")
        return runs, str(next_cursor) if next_cursor else None

    async def get_run(self, agent_id: str, run_id: str) -> RunRef:
        response = await self._request(
            "GET", f"/v1/agents/{agent_id}/runs/{run_id}"
        )
        payload = response.json()
        run_payload = payload.get("run") if isinstance(payload, dict) else None
        if isinstance(run_payload, dict):
            return _run_from_payload(run_payload, default_agent_id=agent_id)
        return _run_from_payload(payload, default_agent_id=agent_id)

    async def cancel_run(self, agent_id: str, run_id: str) -> None:
        await self._request(
            "POST", f"/v1/agents/{agent_id}/runs/{run_id}/cancel"
        )

    async def stream_run(
        self,
        agent_id: str,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[SseEvent]:
        headers = {
            "Accept": "text/event-stream",
            "Authorization": _auth_header(self._api_key),
        }
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        url = f"{self._base_url}/v1/agents/{agent_id}/runs/{run_id}/stream"
        async with self._client.stream("GET", url, headers=headers) as response:
            if response.status_code == 410:
                body = await response.aread()
                try:
                    raw = json.loads(body.decode("utf-8", errors="replace"))
                    payload = raw if isinstance(raw, dict) else {}
                except Exception:
                    payload = {}
                raise CursorStreamExpiredError(
                    str(payload.get("message") or "stream expired"),
                    status_code=410,
                    code=str(payload.get("code") or "stream_expired"),
                )
            if response.status_code >= 400:
                body = await response.aread()
                raise CursorCloudError(
                    body.decode("utf-8", errors="replace") or f"HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            async def _chunks() -> AsyncIterator[bytes]:
                async for chunk in response.aiter_bytes():
                    yield chunk

            async for event in parse_sse_stream(_chunks()):
                yield event

    async def get_usage(
        self,
        agent_id: str,
        *,
        run_id: str | None = None,
    ) -> tuple[UsageBreakdown, dict[str, UsageBreakdown]]:
        params = {"runId": run_id} if run_id else None
        response = await self._request(
            "GET", f"/v1/agents/{agent_id}/usage", params=params
        )
        payload = response.json()
        total = _usage_from_mapping(payload.get("totalUsage") or payload.get("total_usage"))
        runs: dict[str, UsageBreakdown] = {}
        for item in payload.get("runs") or []:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("id") or "")
            if rid:
                runs[rid] = _usage_from_mapping(item.get("usage"))
        return total, runs

    async def list_artifacts(self, agent_id: str) -> list[ArtifactRef]:
        response = await self._request("GET", f"/v1/agents/{agent_id}/artifacts")
        payload = response.json()
        items = payload.get("artifacts") or payload.get("items") or []
        artifacts: list[ArtifactRef] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("absolutePath") or "").strip()
            if not path:
                continue
            artifacts.append(
                ArtifactRef(
                    path=path,
                    size_bytes=int(item["sizeBytes"])
                    if item.get("sizeBytes") is not None
                    else None,
                    updated_at=str(item.get("updatedAt") or "") or None,
                )
            )
        return artifacts

    async def download_artifact_url(self, agent_id: str, path: str) -> str:
        response = await self._request(
            "GET",
            f"/v1/agents/{agent_id}/artifacts/download",
            params={"path": path},
        )
        payload = response.json()
        url = str(payload.get("url") or "").strip()
        if not url:
            raise CursorCloudError("artifact download URL missing")
        return url

    async def download_artifact_bytes(self, agent_id: str, path: str) -> bytes:
        url = await self.download_artifact_url(agent_id, path)
        response = await self._client.get(url)
        if response.status_code >= 400:
            raise CursorCloudError(
                f"artifact download failed: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response.content

    async def archive_agent(self, agent_id: str) -> None:
        await self._request("POST", f"/v1/agents/{agent_id}/archive")

    async def unarchive_agent(self, agent_id: str) -> None:
        await self._request("POST", f"/v1/agents/{agent_id}/unarchive")

    async def delete_agent(self, agent_id: str) -> None:
        await self._request("DELETE", f"/v1/agents/{agent_id}")

    async def me(self) -> dict[str, Any]:
        response = await self._request("GET", "/v1/me")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def list_models(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/v1/models")
        payload = response.json()
        items = payload.get("items") or payload.get("models") or []
        return [item for item in items if isinstance(item, dict)]

    async def list_repositories(self) -> list[str]:
        response = await self._request("GET", "/v1/repositories")
        payload = response.json()
        items = payload.get("items") or payload.get("repositories") or []
        urls: list[str] = []
        for item in items:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                url = item.get("url") or item.get("repository")
                if url:
                    urls.append(str(url))
        return urls


def _prompt_body(
    text: str,
    images: Sequence[PromptImage] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text}
    if images:
        body["images"] = [
            {"data": image.data, "mimeType": image.mime_type}
            for image in images[:5]
        ]
    return body


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _agent_from_payload(payload: Mapping[str, Any]) -> AgentRef:
    return AgentRef(
        id=str(payload.get("id") or ""),
        status=str(payload.get("status") or "") or None,
        url=str(payload.get("url") or "") or None,
        name=str(payload.get("name") or "") or None,
        latest_run_id=str(payload.get("latestRunId") or "") or None,
        raw=dict(payload),
    )


def _run_from_payload(
    payload: Mapping[str, Any],
    *,
    default_agent_id: str,
) -> RunRef:
    git = payload.get("git")
    return RunRef(
        id=str(payload.get("id") or ""),
        agent_id=str(payload.get("agentId") or default_agent_id),
        status=str(payload.get("status") or "CREATING"),
        result=str(payload.get("result") or "") or None,
        duration_ms=int(payload["durationMs"])
        if payload.get("durationMs") is not None
        else None,
        git=dict(git) if isinstance(git, Mapping) else None,
        raw=dict(payload),
    )
