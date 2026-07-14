"""Tests for Telegram Mini App URL helpers."""

from beachops.services.webapp_url import webapp_open_url


def test_webapp_open_url_passthrough_without_version() -> None:
    assert webapp_open_url("https://beachops.example.com") == (
        "https://beachops.example.com"
    )


def test_webapp_open_url_appends_version() -> None:
    assert webapp_open_url(
        "https://beachops.example.com",
        version="b734e9d",
    ) == "https://beachops.example.com?v=b734e9d"


def test_webapp_open_url_preserves_existing_query() -> None:
    assert webapp_open_url(
        "https://beachops.example.com/?tab=voice",
        version="abc",
    ) == "https://beachops.example.com/?tab=voice&v=abc"
