"""Smoke tests: critical modules import without side effects."""


def test_import_telegram_stream_renderer() -> None:
    from tg_cursor_bot.services.telegram_renderer import TelegramStreamRenderer

    assert TelegramStreamRenderer is not None


def test_import_app_factory() -> None:
    from tg_cursor_bot.app import create_application

    assert create_application is not None
