"""Tests for prompt coalesce helpers."""

from __future__ import annotations

from types import SimpleNamespace

from beachops.services.prompt_coalesce import PromptCoalesceBuffer, _compose_prompt
from beachops.services.ui_copy import photo_default_prompt


def _msg(*, message_id: int, caption: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(message_id=message_id, caption=caption)


def test_compose_prompt_prefers_text_then_unique_caption() -> None:
    photos = [_msg(message_id=1, caption="смотри скрин")]
    assert _compose_prompt(["почини баг"], photos) == "почини баг\n\nсмотри скрин"


def test_compose_prompt_dedupes_identical_text_and_caption() -> None:
    photos = [_msg(message_id=1, caption="одно и то же")]
    assert _compose_prompt(["одно и то же"], photos) == "одно и то же"


def test_compose_prompt_caption_only() -> None:
    photos = [_msg(message_id=2, caption="только подпись")]
    assert _compose_prompt([], photos) == "только подпись"


def test_compose_prompt_default_without_text() -> None:
    assert _compose_prompt([], []) == photo_default_prompt()


def test_coalesce_has_pending_tracks_content() -> None:
    buf = PromptCoalesceBuffer(delay_sec=5.0, max_images=20)
    assert not buf.has_pending(1)
    buf._pending[1] = buf._ensure_locked(1)
    buf._pending[1].texts.append("hi")
    assert buf.has_pending(1)
