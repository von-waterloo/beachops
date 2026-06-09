"""Cursor Cloud Agents integration via cursor-sdk."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cursor_sdk import (
    AgentOptions,
    AsyncClient,
    CloudAgentOptions,
    CloudRepository,
    CursorAgentError,
    ModelSelection,
    SDKImage,
    SendOptions,
    UserMessage,
)

from tg_cursor_bot.domain.models import RepoConfig, UserMode
from tg_cursor_bot.domain.prompts import build_prompt
from tg_cursor_bot.services.stream_bridge import StreamState

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
    ) -> tuple[RunOutcome, str | None]:
        cursor_mode = "agent" if mode in (UserMode.ASK, UserMode.DO) else "plan"
        auto_create_pr = mode == UserMode.DO
        full_prompt = build_prompt(
            prompt,
            mode,
            default_branch=repo.default_branch,
            memory_block=memory_block,
        )

        state = StreamState()
        new_agent_id: str | None = None

        try:
            async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
                async with await self._open_agent(
                    client,
                    cursor_agent_id=cursor_agent_id,
                    repo=repo,
                    model=model,
                    cursor_mode=cursor_mode,
                    auto_create_pr=auto_create_pr,
                ) as agent:
                    send_options = SendOptions(mode=cursor_mode, model=model)
                    payload: str | UserMessage = (
                        UserMessage(text=full_prompt, images=tuple(images))
                        if images
                        else full_prompt
                    )
                    outcome = await self._run_single_send(
                        agent,
                        payload,
                        state,
                        on_update,
                        send_options,
                    )
                    new_agent_id = agent.agent_id

                    return outcome, new_agent_id
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
        state.final_text = result.result or state.assistant_text
        if result.git and result.git.branches:
            for branch in result.git.branches:
                if branch.pr_url:
                    state.pr_url = branch.pr_url
                    break
        state.duration_ms = result.duration_ms
        if state.final_text and not state.assistant_text:
            state.assistant_text = state.final_text
        await on_update(state)

        if result.status == "error":
            return RunOutcome(state, result.status, "Run finished with error status")
        return RunOutcome(state, result.status)

    async def cancel_run(self, cursor_agent_id: str, run_id: str) -> bool:
        try:
            async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
                run = await client.agents.get_run(
                    run_id,
                    {"agentId": cursor_agent_id, "apiKey": self._api_key},
                )
                if run.status == "running":
                    await client.agents.cancel_run(run_id, agent_id=cursor_agent_id)
                    return True
                return False
        except CursorAgentError:
            logger.exception("Failed to cancel run %s", run_id)
            return False

    async def archive_agent(self, cursor_agent_id: str) -> None:
        try:
            async with await AsyncClient.launch_bridge(workspace=str(self._workspace)) as client:
                await client.agents.archive(cursor_agent_id)
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
    ):
        cloud = CloudAgentOptions(
            repos=[
                CloudRepository(
                    url=repo.github_url,
                    starting_ref=repo.default_branch,
                )
            ],
            auto_create_pr=auto_create_pr,
            skip_reviewer_request=True,
        )
        options = AgentOptions(
            api_key=self._api_key,
            model=model,
            cloud=cloud,
            mode=cursor_mode,
        )
        if cursor_agent_id:
            return await client.agents.resume(cursor_agent_id, options)
        return await client.agents.create(options)

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
        elif msg_type == "status":
            status = getattr(message, "status", None) or message.get("status")
            if status:
                state.status = str(status)

        await on_update(state)
