"""Fetch and deliver Cursor cloud artifacts after a run."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath
from uuid import UUID

from telegram import Bot

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.services.cursor_cloud_client import CursorCloudError
from beachops.services.plan_format import PLAN_ARTIFACT_SUFFIX
from beachops.services.stream_bridge import StreamState
from beachops.services.ui_copy import answer_document_caption, plan_document_caption

logger = logging.getLogger(__name__)

_MAX_ARTIFACTS = 5
_MAX_BYTES = 15 * 1024 * 1024
_ALLOWED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".webm",
    ".md",
    ".txt",
    ".pdf",
}


def _safe_artifact_path(path: str) -> str | None:
    cleaned = (path or "").replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        return None
    if cleaned.startswith("opt/cursor/artifacts/"):
        cleaned = cleaned[len("opt/cursor/") :]
    if not cleaned.startswith("artifacts/"):
        cleaned = f"artifacts/{cleaned}" if not cleaned.startswith("/") else cleaned
    suffix = PurePosixPath(cleaned).suffix.lower()
    if suffix and suffix not in _ALLOWED_SUFFIXES:
        return None
    return cleaned


async def deliver_run_artifacts(
    app: AppContext,
    bot: Bot,
    *,
    job_id: UUID,
    actor_id: int,
    agent_id: str | None,
    mode: UserMode,
    state: StreamState,
) -> int:
    if not agent_id:
        return 0
    slot = await app.agent_slots.get_active(actor_id)
    token_key = None
    if slot is not None:
        token_key = slot.cursor_token_key
    api_key = app.settings.cursor_api_key_for(token_key)
    try:
        artifacts = await app.cursor.list_artifacts(agent_id, api_key=api_key)
    except CursorCloudError:
        logger.warning("list_artifacts failed for %s", agent_id, exc_info=True)
        return 0

    delivered = 0
    for artifact in artifacts:
        if delivered >= _MAX_ARTIFACTS:
            break
        path = _safe_artifact_path(artifact.path)
        if path is None:
            continue
        if path.endswith(PLAN_ARTIFACT_SUFFIX):
            # Plan already rendered into Telegram / document fallback.
            continue
        if artifact.size_bytes is not None and artifact.size_bytes > _MAX_BYTES:
            continue
        try:
            data = await app.cursor.download_artifact(agent_id, path, api_key=api_key)
        except CursorCloudError:
            logger.warning("download artifact failed: %s", path, exc_info=True)
            continue
        if not data or len(data) > _MAX_BYTES:
            continue

        filename = PurePosixPath(path).name or "artifact.bin"
        mime, _ = mimetypes.guess_type(filename)
        await app.jobs.add_artifact(
            actor_id,
            job_id,
            artifact_kind=mime or "file",
            uri=path,
            metadata={
                "filename": filename,
                "sizeBytes": len(data),
                "mime": mime,
            },
        )
        caption = (
            plan_document_caption(state.plan_name)
            if mode == UserMode.PLAN
            else answer_document_caption()
        )
        try:
            if mime and mime.startswith("image/"):
                await bot.send_photo(
                    chat_id=actor_id,
                    photo=data,
                    caption=f"🖼 {filename}",
                )
            elif mime and mime.startswith("video/"):
                await bot.send_video(
                    chat_id=actor_id,
                    video=data,
                    caption=f"🎬 {filename}",
                )
            else:
                await bot.send_document(
                    chat_id=actor_id,
                    document=data,
                    filename=filename,
                    caption=caption if filename.endswith(".md") else f"📎 {filename}",
                )
            delivered += 1
        except Exception:
            logger.warning("Telegram artifact send failed for %s", filename, exc_info=True)
    return delivered
