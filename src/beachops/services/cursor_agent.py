"""Cursor Cloud Agents integration via Cloud Agents API v1."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from beachops.domain.models import RepoConfig, UserMode
from beachops.domain.prompts import build_prompt, is_protected_default_branch
from beachops.domain.runtime import AgentRuntime, parse_runtime
from beachops.services.cursor_cloud_client import (
    ArtifactRef,
    CursorAgentBusyError,
    CursorCloudClient,
    CursorCloudError,
    CursorStreamExpiredError,
    ModelParam,
    ModelSelection,
    PromptImage,
    RunRef,
    UsageBreakdown,
)
from beachops.services.cursor_sse import (
    extract_git_fields,
    normalize_run_status,
)
from beachops.services.plan_format import (
    PLAN_ARTIFACT_SUFFIX,
    PLAN_TOOL_NAME,
    extract_plan_from_tool_args,
    plan_title,
    split_plan_frontmatter,
)
from beachops.services.redaction import redact_text
from beachops.services.stream_bridge import StreamState

logger = logging.getLogger(__name__)

OnStreamUpdate = Callable[[StreamState], Awaitable[None]]
DEFAULT_API_BASE = "https://api.cursor.com"


@dataclass
class RunOutcome:
    state: StreamState
    status: str
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class StartedRun:
    agent_id: str
    run_id: str
    state: StreamState


def model_selection_from_sdk_or_dict(
    model: str | ModelSelection | Any,
) -> ModelSelection | str:
    """Accept BeachOps ModelSelection, plain id, or legacy cursor_sdk ModelSelection."""
    if isinstance(model, ModelSelection):
        return model
    if isinstance(model, str):
        return model
    model_id = getattr(model, "id", None)
    if isinstance(model_id, str) and model_id:
        params_raw = getattr(model, "params", ()) or ()
        params: list[ModelParam] = []
        for item in params_raw:
            pid = getattr(item, "id", None)
            pval = getattr(item, "value", None)
            if pid is not None and pval is not None:
                params.append(ModelParam(id=str(pid), value=str(pval)))
        return ModelSelection(id=model_id, params=tuple(params))
    return str(model)


def prompt_images_from_any(images: Sequence[Any] | None) -> list[PromptImage]:
    """Convert SDK images / bytes payloads into REST PromptImage list."""
    if not images:
        return []
    out: list[PromptImage] = []
    for item in images:
        if isinstance(item, PromptImage):
            out.append(item)
            continue
        mime = getattr(item, "mime_type", None) or getattr(item, "mimeType", None)
        data = getattr(item, "data", None)
        if callable(getattr(item, "to_base64", None)):
            try:
                data = item.to_base64()
            except Exception:
                data = getattr(item, "data", None)
        if isinstance(data, bytes):
            b64 = base64.b64encode(data).decode("ascii")
            mime_s = str(mime or "image/png")
            out.append(PromptImage(data=b64, mime_type=mime_s))
        elif isinstance(data, str) and data:
            out.append(PromptImage(data=data, mime_type=str(mime or "image/png")))
    return out[:5]


class CursorAgentService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        workspace: Path,
        mcp_enabled: bool = False,
        mcp_public_url: str = "",
        mcp_bearer_token: str = "",
        api_base_url: str = DEFAULT_API_BASE,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._workspace = workspace
        self._mcp_enabled = mcp_enabled
        self._mcp_public_url = (mcp_public_url or "").strip()
        self._mcp_bearer_token = (mcp_bearer_token or "").strip()
        self._api_base_url = (api_base_url or DEFAULT_API_BASE).rstrip("/")

    def _client(self, api_key: str | None = None) -> CursorCloudClient:
        return CursorCloudClient(
            api_key=api_key or self._api_key,
            base_url=self._api_base_url,
        )

    def _mcp_servers(self) -> list[dict[str, Any]] | None:
        if not self._mcp_enabled or not self._mcp_public_url or not self._mcp_bearer_token:
            return None
        return [
            {
                "name": "beachops-ops",
                "type": "http",
                "url": self._mcp_public_url,
                "headers": {"Authorization": f"Bearer {self._mcp_bearer_token}"},
            }
        ]

    async def run_prompt(
        self,
        *,
        prompt: str,
        mode: UserMode,
        repo: RepoConfig,
        model: str | ModelSelection | Any,
        cursor_agent_id: str | None,
        on_update: OnStreamUpdate,
        memory_block: str | None = None,
        situation_block: str | None = None,
        images: Sequence[Any] | None = None,
        api_key: str | None = None,
        runtime: str | AgentRuntime | None = None,
        local_path: str | None = None,
        self_improve: bool = False,
        channel: str | None = None,
        last_event_id: str | None = None,
    ) -> tuple[RunOutcome, str | None]:
        del local_path  # cloud-only path
        resolved_runtime = parse_runtime(runtime)
        if resolved_runtime == AgentRuntime.WINDOWS:
            resolved_runtime = AgentRuntime.CLOUD

        cursor_mode = "agent" if mode in (UserMode.ASK, UserMode.DO) else "plan"
        protected_base = is_protected_default_branch(repo.default_branch)
        work_on_current_branch = mode == UserMode.DO and not protected_base
        auto_create_pr = mode == UserMode.DO and protected_base
        full_prompt = build_prompt(
            prompt,
            mode,
            default_branch=repo.default_branch,
            memory_block=memory_block,
            situation_block=situation_block,
            self_improve=self_improve,
            channel=channel,
        )
        state = StreamState()
        key = api_key or self._api_key
        try:
            started = await self.start_run(
                prompt=full_prompt,
                mode=cursor_mode,
                repo=repo,
                model=model,
                cursor_agent_id=cursor_agent_id,
                images=images,
                api_key=key,
                auto_create_pr=auto_create_pr,
                work_on_current_branch=work_on_current_branch,
                on_update=on_update,
                state=state,
            )
            outcome = await self.observe_run(
                agent_id=started.agent_id,
                run_id=started.run_id,
                state=started.state,
                on_update=on_update,
                api_key=key,
                last_event_id=last_event_id,
                plan_mode=cursor_mode == "plan",
            )
            return outcome, started.agent_id
        except CursorAgentBusyError as exc:
            if cursor_agent_id:
                logger.warning("AgentBusy for %s; attaching to active run", cursor_agent_id)
                outcome = await self._attach_active_run(
                    cursor_agent_id,
                    state,
                    on_update,
                    api_key=key,
                    plan_mode=cursor_mode == "plan",
                )
                return outcome, cursor_agent_id
            logger.warning("Cursor agent busy: %s", exc.message)
            return (
                RunOutcome(state, "error", f"Cursor error: {exc.message}"),
                cursor_agent_id,
            )
        except CursorCloudError as exc:
            logger.exception("Cursor startup/run error: %s", exc.message)
            return (
                RunOutcome(state, "error", _friendly_cursor_error(exc.message)),
                cursor_agent_id,
            )

    async def start_run(
        self,
        *,
        prompt: str,
        mode: str,
        repo: RepoConfig,
        model: str | ModelSelection | Any,
        cursor_agent_id: str | None,
        images: Sequence[Any] | None = None,
        api_key: str | None = None,
        auto_create_pr: bool = False,
        work_on_current_branch: bool = False,
        on_update: OnStreamUpdate | None = None,
        state: StreamState | None = None,
    ) -> StartedRun:
        state = state or StreamState()
        model_sel = model_selection_from_sdk_or_dict(model)
        prompt_images = prompt_images_from_any(images)
        mcp = self._mcp_servers()
        async with self._client(api_key) as client:
            if cursor_agent_id:
                run = await client.create_run(
                    cursor_agent_id,
                    prompt_text=prompt,
                    mode=mode,
                    images=prompt_images or None,
                    mcp_servers=mcp,
                )
                agent_id = cursor_agent_id
            else:
                agent, run = await client.create_agent(
                    prompt_text=prompt,
                    repo_url=repo.github_url,
                    starting_ref=repo.default_branch,
                    model=model_sel,
                    mode=mode,
                    images=prompt_images or None,
                    auto_create_pr=auto_create_pr,
                    work_on_current_branch=work_on_current_branch,
                    mcp_servers=mcp,
                )
                agent_id = agent.id
        state.agent_id = agent_id
        state.run_id = run.id
        state.status = normalize_run_status(run.status)
        if on_update is not None:
            await on_update(state)
        return StartedRun(agent_id=agent_id, run_id=run.id, state=state)

    async def observe_run(
        self,
        *,
        agent_id: str,
        run_id: str,
        state: StreamState,
        on_update: OnStreamUpdate,
        api_key: str | None = None,
        last_event_id: str | None = None,
        plan_mode: bool = False,
        max_reconnects: int = 8,
    ) -> RunOutcome:
        state.agent_id = agent_id
        state.run_id = run_id
        event_id = last_event_id
        reconnects = 0
        while reconnects <= max_reconnects:
            try:
                terminal = await self._consume_sse(
                    agent_id=agent_id,
                    run_id=run_id,
                    state=state,
                    on_update=on_update,
                    api_key=api_key,
                    last_event_id=event_id,
                )
                if terminal:
                    break
            except CursorStreamExpiredError:
                logger.info("SSE expired for %s; polling GET run", run_id)
                break
            except CursorCloudError:
                reconnects += 1
                if reconnects > max_reconnects:
                    raise
                logger.warning(
                    "SSE reconnect %s/%s for run %s",
                    reconnects,
                    max_reconnects,
                    run_id,
                    exc_info=True,
                )
                await asyncio.sleep(min(2 ** reconnects, 20))
                event_id = state.last_event_id
                continue
            event_id = state.last_event_id
            if normalize_run_status(state.status) in {
                "finished",
                "error",
                "cancelled",
            }:
                break
            reconnects += 1
            await asyncio.sleep(min(2 ** reconnects, 10))

        snapshot = await self.get_run_snapshot(agent_id, run_id, api_key=api_key)
        _apply_snapshot(state, snapshot)
        await on_update(state)

        if plan_mode:
            await self._finalize_plan(agent_id, state, api_key=api_key)
            await on_update(state)

        usage = await self.fetch_run_usage(agent_id, run_id, api_key=api_key)
        if usage is not None:
            state.input_tokens = usage.input_tokens
            state.output_tokens = usage.output_tokens
            state.cache_read_tokens = usage.cache_read_tokens
            state.cache_write_tokens = usage.cache_write_tokens
            state.total_tokens = usage.total_tokens
            await on_update(state)

        status = normalize_run_status(state.status)
        if status == "error":
            return RunOutcome(state, status, "Run finished with error status")
        return RunOutcome(state, status)

    async def _consume_sse(
        self,
        *,
        agent_id: str,
        run_id: str,
        state: StreamState,
        on_update: OnStreamUpdate,
        api_key: str | None,
        last_event_id: str | None,
    ) -> bool:
        """Return True when a terminal result/done was observed."""
        terminal = False
        async with self._client(api_key) as client:
            async for event in client.stream_run(
                agent_id, run_id, last_event_id=last_event_id
            ):
                if event.id:
                    state.last_event_id = event.id
                etype = event.event
                data = event.data
                if etype == "assistant":
                    text = str(data.get("text") or "")
                    if text:
                        state.append_assistant(text)
                elif etype == "thinking":
                    text = str(data.get("text") or "")
                    if text:
                        state.append_thinking(text)
                elif etype == "tool_call":
                    name = str(data.get("name") or "tool")
                    status = str(data.get("status") or "running")
                    state.upsert_tool(name, status)
                    if name == PLAN_TOOL_NAME:
                        state.plan_tool_called = True
                        plan = extract_plan_from_tool_args(data.get("args"))
                        if plan:
                            state.set_plan(plan)
                elif etype == "status":
                    status = normalize_run_status(str(data.get("status") or ""))
                    if status:
                        state.status = status
                elif etype == "result":
                    status = normalize_run_status(str(data.get("status") or "finished"))
                    state.status = status
                    text = data.get("text")
                    if text:
                        state.final_text = redact_text(str(text))
                        if not state.assistant_text:
                            state.assistant_text = state.final_text
                    if data.get("durationMs") is not None:
                        state.duration_ms = int(data["durationMs"])
                    branch, pr_url = extract_git_fields(data)
                    if branch and not state.branch_name:
                        state.branch_name = branch
                    if pr_url:
                        state.pr_url = pr_url
                    terminal = True
                elif etype == "error":
                    state.status = "error"
                    message = str(data.get("message") or "stream error")
                    state.final_text = redact_text(message)
                    terminal = True
                elif etype == "done":
                    terminal = True
                await on_update(state)
                if terminal:
                    break
        return terminal

    async def get_run_snapshot(
        self,
        cursor_agent_id: str,
        run_id: str,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        async with self._client(api_key) as client:
            run = await client.get_run(cursor_agent_id, run_id)
        branch, pr_url = extract_git_fields({"git": run.git} if run.git else None)
        return {
            "status": normalize_run_status(run.status),
            "result": run.result or "",
            "pr_url": pr_url,
            "branch_name": branch,
            "total_tokens": None,
            "duration_ms": run.duration_ms,
            "agent_id": run.agent_id or cursor_agent_id,
            "run_id": run.id,
        }

    async def fetch_run_usage(
        self,
        agent_id: str,
        run_id: str,
        *,
        api_key: str | None = None,
    ) -> UsageBreakdown | None:
        try:
            async with self._client(api_key) as client:
                _total, runs = await client.get_usage(agent_id, run_id=run_id)
            return runs.get(run_id) or _total
        except CursorCloudError:
            logger.warning("Could not fetch usage for %s/%s", agent_id, run_id, exc_info=True)
            return None

    async def list_artifacts(
        self,
        agent_id: str,
        *,
        api_key: str | None = None,
    ) -> list[ArtifactRef]:
        async with self._client(api_key) as client:
            return await client.list_artifacts(agent_id)

    async def download_artifact(
        self,
        agent_id: str,
        path: str,
        *,
        api_key: str | None = None,
    ) -> bytes:
        async with self._client(api_key) as client:
            return await client.download_artifact_bytes(agent_id, path)

    async def _attach_active_run(
        self,
        agent_id: str,
        state: StreamState,
        on_update: OnStreamUpdate,
        *,
        api_key: str,
        plan_mode: bool,
    ) -> RunOutcome:
        async with self._client(api_key) as client:
            runs, _ = await client.list_runs(agent_id, limit=5)
        active: RunRef | None = None
        for item in runs:
            if normalize_run_status(item.status) == "running":
                active = item
                break
        if active is None and runs:
            active = runs[0]
        if active is None:
            return RunOutcome(state, "error", "Agent busy but no run found")
        state.run_id = active.id
        state.agent_id = agent_id
        state.status = normalize_run_status(active.status)
        await on_update(state)
        return await self.observe_run(
            agent_id=agent_id,
            run_id=active.id,
            state=state,
            on_update=on_update,
            api_key=api_key,
            plan_mode=plan_mode,
        )

    async def cancel_run(
        self,
        cursor_agent_id: str,
        run_id: str,
        *,
        api_key: str | None = None,
    ) -> bool:
        try:
            async with self._client(api_key) as client:
                run = await client.get_run(cursor_agent_id, run_id)
                if normalize_run_status(run.status) == "running":
                    await client.cancel_run(cursor_agent_id, run_id)
                    return True
                return False
        except CursorCloudError:
            logger.exception("Failed to cancel run %s", run_id)
            return False

    async def archive_agent(
        self,
        cursor_agent_id: str,
        *,
        api_key: str | None = None,
    ) -> None:
        try:
            async with self._client(api_key) as client:
                await client.archive_agent(cursor_agent_id)
        except CursorCloudError:
            logger.warning("Could not archive agent %s", cursor_agent_id, exc_info=True)

    async def unarchive_agent(
        self,
        cursor_agent_id: str,
        *,
        api_key: str | None = None,
    ) -> None:
        async with self._client(api_key) as client:
            await client.unarchive_agent(cursor_agent_id)

    async def delete_agent(
        self,
        cursor_agent_id: str,
        *,
        api_key: str | None = None,
    ) -> None:
        async with self._client(api_key) as client:
            await client.delete_agent(cursor_agent_id)

    async def get_agent(
        self,
        cursor_agent_id: str,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        async with self._client(api_key) as client:
            agent = await client.get_agent(cursor_agent_id)
        return dict(agent.raw)

    async def list_agents(
        self,
        *,
        api_key: str | None = None,
        limit: int = 50,
        include_archived: bool = True,
    ) -> list[dict[str, Any]]:
        async with self._client(api_key) as client:
            agents, _ = await client.list_agents(
                limit=limit, include_archived=include_archived
            )
        return [dict(agent.raw) for agent in agents]

    async def _finalize_plan(
        self,
        agent_id: str,
        state: StreamState,
        *,
        api_key: str | None,
    ) -> None:
        if not state.plan_text and state.plan_tool_called:
            await self._fetch_plan_artifact(agent_id, state, api_key=api_key)
        if not state.plan_text:
            return
        if not state.plan_name:
            state.plan_name = plan_title(state.plan_text)
        intro = (state.final_text or "").strip()
        if intro and intro not in state.plan_text and len(intro) < 400:
            state.final_text = f"{intro}\n\n{state.plan_text}"
        else:
            state.final_text = state.plan_text

    async def _fetch_plan_artifact(
        self,
        agent_id: str,
        state: StreamState,
        *,
        api_key: str | None,
    ) -> None:
        try:
            artifacts = await self.list_artifacts(agent_id, api_key=api_key)
        except CursorCloudError:
            logger.warning("Could not list plan artifacts", exc_info=True)
            return
        plans = [a for a in artifacts if a.path.endswith(PLAN_ARTIFACT_SUFFIX)]
        if not plans:
            return
        newest = max(plans, key=lambda a: a.updated_at or "")
        try:
            data = await self.download_artifact(agent_id, newest.path, api_key=api_key)
        except CursorCloudError:
            logger.warning(
                "Could not download plan artifact %s", newest.path, exc_info=True
            )
            return
        name, body = split_plan_frontmatter(data.decode("utf-8", errors="replace"))
        if body:
            state.set_plan(body, name=name)


def _apply_snapshot(state: StreamState, snapshot: dict[str, Any]) -> None:
    state.status = normalize_run_status(str(snapshot.get("status") or state.status))
    result = redact_text(str(snapshot.get("result") or ""))
    if result:
        state.final_text = result
        if not state.assistant_text:
            state.assistant_text = result
    if snapshot.get("pr_url"):
        state.pr_url = str(snapshot["pr_url"])
    if snapshot.get("branch_name") and not state.branch_name:
        state.branch_name = str(snapshot["branch_name"])
    if snapshot.get("duration_ms") is not None:
        state.duration_ms = int(snapshot["duration_ms"])
    if snapshot.get("total_tokens") is not None:
        state.total_tokens = int(snapshot["total_tokens"])


def _friendly_cursor_error(message: str) -> str:
    lower = (message or "").lower()
    if "failed to verify existence of branch" in lower or (
        "branch" in lower and "repository" in lower and "verify" in lower
    ):
        return (
            "Cursor не видит ветку репозитория. Проверьте: ветка существует на GitHub; "
            "у аккаунта CURSOR_API_KEY есть GitHub-доступ к этому репо "
            "(Cursor → Settings → GitHub). "
            f"Детали: {message}"
        )
    return f"Cursor error: {message}"
