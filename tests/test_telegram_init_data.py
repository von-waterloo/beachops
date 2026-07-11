from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from beachops.web.telegram_auth import (
    TelegramInitDataError,
    extract_tma_authorization,
    validate_init_data,
    validate_login_widget,
)


def _signed_init_data(*, token: str, auth_date: int = 1000, user_id: int = 42) -> str:
    values = {
        "auth_date": str(auth_date),
        "query_id": "query-1",
        "user": json.dumps({"id": user_id, "username": "owner"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def _signed_login_widget(
    *,
    token: str,
    auth_date: int = 1000,
    user_id: int = 42,
) -> dict[str, object]:
    values = {
        "id": str(user_id),
        "first_name": "Owner",
        "username": "owner",
        "auth_date": str(auth_date),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hashlib.sha256(token.encode()).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return values


def test_valid_init_data_returns_principal() -> None:
    raw = _signed_init_data(token="bot-token")
    principal = validate_init_data(raw, "bot-token", now=1005)
    assert principal.user_id == 42
    assert principal.username == "owner"
    assert principal.query_id == "query-1"


def test_init_data_rejects_tampering_and_expiry() -> None:
    raw = _signed_init_data(token="bot-token")
    with pytest.raises(TelegramInitDataError, match="invalid hash"):
        validate_init_data(raw.replace("owner", "attacker"), "bot-token", now=1005)
    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_init_data(raw, "bot-token", now=5000, max_age_sec=60)


def test_extract_tma_authorization() -> None:
    assert extract_tma_authorization("tma abc") == "abc"
    with pytest.raises(TelegramInitDataError):
        extract_tma_authorization("Bearer abc")


def test_valid_login_widget_returns_principal() -> None:
    payload = _signed_login_widget(token="bot-token")
    principal = validate_login_widget(payload, "bot-token", now=1005)
    assert principal.user_id == 42
    assert principal.username == "owner"
    assert principal.auth_method == "telegram_login"


def test_login_widget_rejects_tampering_and_expiry() -> None:
    payload = _signed_login_widget(token="bot-token")
    bad = dict(payload)
    bad["username"] = "attacker"
    with pytest.raises(TelegramInitDataError, match="invalid hash"):
        validate_login_widget(bad, "bot-token", now=1005)
    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_login_widget(payload, "bot-token", now=5000, max_age_sec=60)
