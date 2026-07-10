"""Cursor Cloud Agents integration via cursor-sdk."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cursor_sdk import (
    AgentBusyError,
    AgentOptions,
    AsyncClient,
    CloudAgentOptions,
    CloudRepository,
    CursorAgentError,
    LocalAgentOptions,
    ModelSelection,
    SDKImage,
    SendOptions,
    UserMessage,
)

from beachops.domain.models import RepoConfig, UserMode
from beachops.domain.prompts import build_prompt
from beachops.domain.runtime import AgentRuntime, parse_runtime
from beachops.services.plan_format import (
    PLAN_ARTIFACT_SUFFIX,
    PLAN_TOOL_NAME,
    extract_plan_from_tool_args,
    plan_title,
    split_plan_frontmatter,
)
from beachops.services.stream_bridge import StreamState
from beachops.services.redaction import redact_text

logger = logging.getLogger(__name__)

OnStreamUpdate = Callable[[StreamState], Awaitable[None]]


@dataclass
class RunOutcome:
    state: StreamState
    status: str
    error_message: str | None = None


class CursorAgentService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        workspace: Path,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._workspace = workspace

    async def run_prompt(
        self,
        *,
        prompt: str,
        mode: UserMode,
        repo: RepoConfig,
        model: str | ModelSelection,
        cursor_agent_id: str | None,
        on_update: OnStreamUpdate,
        memory_block: str | None = None,
        images: Sequence[SDKImage] | None = None,
        api_key: str | None = None,
        runtime: str | AgentRuntime | None = None,
        local_path: str | None = None,
    ) -> tuple[RunOutcome, str | None]:
        cursor_mode = "agent" if mode in (UserMode.ASK, UserMode.DO) else "plan"
        # Write-runs may create an isolated branch/PR only. Direct work on the
        # configured base branch is never enabled by the control plane.
        auto_create_pr = mode == UserMode.DO
        work_on_current_branch = False
        resolved_runtime = parse_runtime(runtime)
        full_prompt = build_prompt(
            prompt,
            mode,
            default_branch=repo.default_branch,
            memory_block=memory_block,
        )

        state = StreamState()
        new_agent_id: str | None = None
        bridge_workspace = (
            local_path
            if resolved_runtime == AgentRuntime.WINDOWS and local_path
            else str(self._workspace)
        )

        try:
            async with await AsyncClient.launch_bridge(workspace=bridge_workspace) as client:
                async with await self._open_agent(
                    client,
                    cursor_agent_id=cursor_agent_id,
                    repo=repo,
                    model=model,
                    cursor_mode=cursor_mode,
                    auto_create_pr=auto_create_pr,
                    work_on_current_branch=work_on_current_branch,
                    api_key=api_key or self._api_key,
                    runtime=resolved_runtime,
                    local_path=local_path,
                ) as agent:
                    send_options = SendOptions(mode=cursor_mode, model=model)
                    payload: str | UserMessage = (
                        UserMessage(text=full_prompt, images=tuple(images))
                        if images
                        else full_prompt
                    )
                    try:
                        outcome = await self._run_single_send(
                            agent,
                            payload,
                            state,
                            on_update,
                            send_options,
                        )
                    except AgentBusyError:
                        # Agent already has an active run — attach instead of failing.
                        logger.warning(
                            "AgentBusy for %s; attaching to active run",
                            agent.agent_id,
                        )
                        outcome = await self._attach_active_run(
                            client,
                            agent.agent_id,
                            state,
                            on_update,
                            api_key=api_key or self._api_key,
                        )
                    new_agent_id = agent.agent_id

                    if cursor_mode == "plan":
                        await self._finalize_plan(agent, state)
                        await on_update(state)

                    return outcome, new_agent_id
        except AgentBusyError as exc:
            logger.warning("Cursor agent busy: %s", exc.message)
            return (
                RunOutcome(state, "error", f"Cursor error: {exc.message}"),
                cursor_agent_id,
            )
        except CursorAgentError as exc:
            logger.exception("Cursor startup/run error: %s", exc.message)
            return (
                RunOutcome(state, "error", f"Cursor error: {exc.message}"),
                cursor_agent_id,
            )

    async def _run_single_send(
        self,
        agent,
        payload: str | UserMessage,
        state: StreamState,
        on_update: OnStreamUpdate,
        send_options: SendOptions,
    ) -> RunOutcome:
        run = await agent.send(payload, send_options)
        state.run_id = run.id
        state.agent_id = agent.agent_id
        await on_update(state)

        async for message in run.messages():
            await self._consume_message(message, state, on_update)

        result = await run.wait()
        state.status = result.status
        state.final_text = redact_text(result.result or state.assistant_text)
        if result.git and result.git.branches:
            for branch in result.git.branches:
                if branch.branch and not state.branch_name:
                    state.branch_name = branch.branch
                if branch.pr_url:
                    state.pr_url = branch.pr_url
                    break
        state.duration_ms = result.duration_ms
        if result.usage is not None:
            state.input_tokens = result.usage.input_tokens
            state.output_tokens = result.usage.output_tokens
            state.cache_read_tokens = result.usage.cache_read_tokens
            state.cache_write_tokens = result.usage.cache_write_tokens
            state.total_tokens = result.usage.total_tokens
            state.reasoning_tokens = result.usage.reasoning_tokens
        if state.final_text and not state.assistant_text:
            state.assistant_text = state.final_text
        await on_update(state)

        if result.status == "error":
            return RunOutcome(state, result.status, "Run finished with error status")
        return RunOutcome(state, result.status)

    async def get_run_snapshot(
        self,
        cursor_agent_id: str,
        run_id: str,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Fetch terminal-friendly run metadata for reconciliation."""
        async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
            run = await client.agents.get_run(
                run_id,
                {"agentId": cursor_agent_id, "apiKey": api_key or self._api_key},
            )
            pr_url = None
            if run.git and run.git.branches:
                for branch in run.git.branches:
                    if branch.pr_url:
                        pr_url = branch.pr_url
                        break
            total_tokens = None
            if run.usage is not None:
                total_tokens = run.usage.total_tokens
            return {
                "status": run.status,
                "result": run.result or "",
                "pr_url": pr_url,
                "total_tokens": total_tokens,
                "duration_ms": run.duration_ms,
                "agent_id": run.agent_id or cursor_agent_id,
                "run_id": run.id,
            }

    async def _attach_active_run(
        self,
        client: AsyncClient,
        agent_id: str,
        state: StreamState,
        on_update: OnStreamUpdate,
        *,
        api_key: str,
    ) -> RunOutcome:
        """Join an already-running Cursor run instead of starting a duplicate."""
        runs = await client.agents.list_runs(
            agent_id,
            api_key=api_key,
            limit=5,
        )
        active = None
        for item in runs.items:
            if str(item.status).lower() in {"running", "in_progress"}:
                active = item
                break
        if active is None and runs.items:
            active = runs.items[0]
        if active is None:
            return RunOutcome(state, "error", "Agent busy but no run found")

        state.run_id = active.id
        state.agent_id = agent_id
        state.status = str(active.status)
        await on_update(state)

        # Prefer live wait when the handle supports it; otherwise poll snapshot.
        try:
            if active.supports("wait"):
                result = await active.wait()
                state.status = result.status
                state.final_text = redact_text(result.result or state.assistant_text)
                if result.git and result.git.branches:
                    for branch in result.git.branches:
                        if branch.pr_url:
                            state.pr_url = branch.pr_url
                            break
                state.duration_ms = result.duration_ms
                if result.usage is not None:
                    state.total_tokens = result.usage.total_tokens
                await on_update(state)
                if result.status == "error":
                    return RunOutcome(state, result.status, "Run finished with error status")
                return RunOutcome(state, result.status)
        except Exception:
            logger.warning("Attach wait failed; falling back to snapshot", exc_info=True)

        snapshot = await self.get_run_snapshot(agent_id, active.id, api_key=api_key)
        state.status = str(snapshot.get("status") or "error")
        state.final_text = redact_text(str(snapshot.get("result") or ""))
        state.pr_url = snapshot.get("pr_url")  # type: ignore[assignment]
        state.total_tokens = snapshot.get("total_tokens")  # type: ignore[assignment]
        await on_update(state)
        if state.status == "error":
            return RunOutcome(state, "error", "Run finished with error status")
        return RunOutcome(state, state.status or "finished")

    async def cancel_run(
        self,
        cursor_agent_id: str,
        run_id: str,
        *,
        api_key: str | None = None,
    ) -> bool:
        try:
            async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
                run = await client.agents.get_run(
                    run_id,
                    {"agentId": cursor_agent_id, "apiKey": api_key or self._api_key},
                )
                if run.status == "running":
                    await client.agents.cancel_run(run_id, agent_id=cursor_agent_id)
                    return True
                return False
        except CursorAgentError:
            logger.exception("Failed to cancel run %s", run_id)
            return False

    async def archive_agent(
        self,
        cursor_agent_id: str,
        *,
        api_key: str | None = None,
    ) -> None:
        try:
            async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
                await client.agents.archive(
                    cursor_agent_id,
                    {"apiKey": api_key or self._api_key},
                )
        except CursorAgentError:
            logger.warning("Could not archive agent %s", cursor_agent_id, exc_info=True)

    async def _open_agent(
        self,
        client: AsyncClient,
        *,
        cursor_agent_id: str | None,
        repo: RepoConfig,
        model: str | ModelSelection,
        cursor_mode: str,
        auto_create_pr: bool,
        work_on_current_branch: bool,
        api_key: str,
        runtime: AgentRuntime = AgentRuntime.CLOUD,
        local_path: str | None = None,
    ):
        if runtime == AgentRuntime.WINDOWS:
            if not local_path:
                raise CursorAgentError(
                    "local_path is required for Windows runtime",
                    code="missing_local_path",
                )
            options = AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=local_path),
                mode=cursor_mode,
            )
        else:
            cloud = CloudAgentOptions(
                repos=[
                    CloudRepository(
                        url=repo.github_url,
                        starting_ref=repo.default_branch,
                    )
                ],
                auto_create_pr=auto_create_pr,
                work_on_current_branch=work_on_current_branch,
                skip_reviewer_request=True,
            )
            options = AgentOptions(
                api_key=api_key,
                model=model,
                cloud=cloud,
                mode=cursor_mode,
            )
        if cursor_agent_id:
            return await client.agents.resume(cursor_agent_id, options)
        return await client.agents.create(options)

    async def _finalize_plan(self, agent, state: StreamState) -> None:
        """Make the plan the final answer of a plan-mode run.

        The `create_plan` tool call carries the full markdown in args; the
        run's `result` is only a short intro phrase. If the tool args were
        not observed (e.g. stream hiccup), fall back to the plan artifact.
        The artifact fallback is gated on `plan_tool_called` so a resumed
        agent's stale plan is never shown for a run that produced no plan
        (e.g. the agent only asked clarifying questions).
        """
        if not state.plan_text and state.plan_tool_called:
            await self._fetch_plan_artifact(agent, state)
        if not state.plan_text:
            return
        if not state.plan_name:
            state.plan_name = plan_title(state.plan_text)
        intro = (state.final_text or "").strip()
        if intro and intro not in state.plan_text and len(intro) < 400:
            state.final_text = f"{intro}\n\n{state.plan_text}"
        else:
            state.final_text = state.plan_text

    async def _fetch_plan_artifact(self, agent, state: StreamState) -> None:
        try:
            artifacts = await agent.list_artifacts()
        except CursorAgentError:
            logger.warning("Could not list plan artifacts", exc_info=True)
            return
        plans = [a for a in artifacts if a.path.endswith(PLAN_ARTIFACT_SUFFIX)]
        if not plans:
            return
        newest = max(plans, key=lambda a: a.updated_at or "")
        try:
            data = await agent.download_artifact(newest.path)
        except CursorAgentError:
            logger.warning("Could not download plan artifact %s", newest.path, exc_info=True)
            return
        name, body = split_plan_frontmatter(data.decode("utf-8", errors="replace"))
        if body:
            state.set_plan(body, name=name)

    async def _consume_message(self, message, state: StreamState, on_update: OnStreamUpdate) -> None:
        msg_type = getattr(message, "type", None) or message.get("type")

        if msg_type == "assistant":
            content = getattr(message, "message", None)
            blocks = getattr(content, "content", None) if content else message.get("message", {}).get("content", [])
            for block in blocks or []:
                block_type = getattr(block, "type", None) or block.get("type")
                if block_type == "text":
                    text = getattr(block, "text", None) or block.get("text", "")
                    state.append_assistant(text)
        elif msg_type == "thinking":
            text = getattr(message, "text", None) or message.get("text", "")
            if text:
                state.append_thinking(text)
        elif msg_type == "tool_call":
            name = getattr(message, "name", None) or message.get("name", "tool")
            status = getattr(message, "status", None) or message.get("status", "running")
            state.upsert_tool(str(name), str(status))
            if str(name) == PLAN_TOOL_NAME:
                state.plan_tool_called = True
                args = getattr(message, "args", None)
                if args is None and isinstance(message, dict):
                    args = message.get("args")
                plan = extract_plan_from_tool_args(args)
                if plan:
                    state.set_plan(plan)
        elif msg_type == "status":
            status = getattr(message, "status", None) or message.get("status")
            if status:
                state.status = str(status)
        elif msg_type == "usage":
            usage = getattr(message, "usage", None)
            if usage is not None:
                state.input_tokens = usage.input_tokens
                state.output_tokens = usage.output_tokens
                state.cache_read_tokens = usage.cache_read_tokens
                state.cache_write_tokens = usage.cache_write_tokens
                state.total_tokens = usage.total_tokens
                state.reasoning_tokens = usage.reasoning_tokens

        await on_update(state)
