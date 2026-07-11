"""Server-side authentication for Telegram Mini Apps."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    """Raised when Telegram Mini App initData cannot be trusted."""


@dataclass(frozen=True)
class TelegramPrincipal:
    user_id: int
    username: str | None
    auth_date: int
    query_id: str | None
    auth_method: str = "telegram"


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_sec: int = 3600,
    now: int | None = None,
) -> TelegramPrincipal:
    """Validate raw Telegram WebApp initData using the Bot API algorithm."""
    if not init_data or not bot_token:
        raise TelegramInitDataError("missing init data")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    received_hash = pairs.pop("hash", "")
    if len(received_hash) != 64:
        raise TelegramInitDataError("missing or malformed hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramInitDataError("invalid hash")

    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramInitDataError("invalid auth date") from exc

    current = int(time.time()) if now is None else now
    if auth_date > current + 30 or current - auth_date > max_age_sec:
        raise TelegramInitDataError("expired init data")

    try:
        user = json.loads(pairs["user"])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramInitDataError("invalid user") from exc

    username = user.get("username")
    return TelegramPrincipal(
        user_id=user_id,
        username=str(username) if username else None,
        auth_date=auth_date,
        query_id=pairs.get("query_id") or None,
    )


def extract_tma_authorization(value: str | None) -> str:
    if not value:
        raise TelegramInitDataError("missing authorization")
    scheme, separator, payload = value.partition(" ")
    if not separator or scheme.lower() != "tma" or not payload:
        raise TelegramInitDataError("invalid authorization scheme")
    return payload


def validate_login_widget(
    payload: dict[str, object],
    bot_token: str,
    *,
    max_age_sec: int = 3600,
    now: int | None = None,
) -> TelegramPrincipal:
    """Validate Telegram Login Widget / OAuth callback payload.

    Algorithm differs from Mini App initData: secret key is SHA256(bot_token).
    See https://core.telegram.org/widgets/login
    """
    if not bot_token:
        raise TelegramInitDataError("missing bot token")
    if not isinstance(payload, dict) or not payload:
        raise TelegramInitDataError("missing login payload")

    received_hash = str(payload.get("hash") or "")
    if len(received_hash) != 64:
        raise TelegramInitDataError("missing or malformed hash")

    check_pairs: dict[str, str] = {}
    for key, value in payload.items():
        if key == "hash" or value is None:
            continue
        check_pairs[str(key)] = str(value)

    data_check_string = "\n".join(
        f"{key}={check_pairs[key]}" for key in sorted(check_pairs)
    )
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramInitDataError("invalid hash")

    try:
        auth_date = int(check_pairs["auth_date"])
        user_id = int(check_pairs["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramInitDataError("invalid login fields") from exc

    current = int(time.time()) if now is None else now
    if auth_date > current + 30 or current - auth_date > max_age_sec:
        raise TelegramInitDataError("expired login data")

    username = check_pairs.get("username") or None
    return TelegramPrincipal(
        user_id=user_id,
        username=username,
        auth_date=auth_date,
        query_id=None,
        auth_method="telegram_login",
    )
