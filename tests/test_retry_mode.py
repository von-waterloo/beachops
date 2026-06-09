"""Tests for history retry mode resolution."""

from __future__ import annotations

from tg_cursor_bot.config.settings import Settings
from tg_cursor_bot.domain.models import UserMode
from tg_cursor_bot.services.run_executor import resolve_history_retry_mode


def _settings(*, admin_ids: list[int]) -> Settings:
    return Settings.model_construct(
        tg_bot_token="t",
        cursor_api_key="k",
        openai_api_key="o",
        admin_user_ids=admin_ids,
        whitelist_user_ids=admin_ids or [1],
    )


def test_resolve_plan_for_admin() -> None:
    settings = _settings(admin_ids=[42])
    assert (
        resolve_history_retry_mode(settings=settings, user_id=42, mode_value="plan")
        == UserMode.PLAN
    )


def test_resolve_plan_denied_for_non_admin() -> None:
    settings = _settings(admin_ids=[])
    assert resolve_history_retry_mode(settings=settings, user_id=1, mode_value="plan") is None


def test_resolve_invalid_mode_falls_back_to_ask() -> None:
    settings = _settings(admin_ids=[])
    assert (
        resolve_history_retry_mode(settings=settings, user_id=1, mode_value="bogus")
        == UserMode.ASK
    )


def test_resolve_none_mode_defaults_to_ask() -> None:
    settings = _settings(admin_ids=[])
    assert (
        resolve_history_retry_mode(settings=settings, user_id=1, mode_value=None)
        == UserMode.ASK
    )
