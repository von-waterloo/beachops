from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from beachops.domain.security import Role
from beachops.web.passkey_auth import (
    _consume_challenge,
    _require_owner_tma,
    _rp_config,
    _session_key,
    _session_principal,
)


class FakeRedis:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> bytes | None:
        return self.values.pop(key, None)

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.values[key] = value


def test_rp_config_uses_public_https_origin() -> None:
    context = SimpleNamespace(
        settings=SimpleNamespace(
            webapp_base_url="https://beachops.marketolog.tech/path"
        )
    )

    assert _rp_config(context) == (
        "beachops.marketolog.tech",
        "https://beachops.marketolog.tech",
    )


def test_session_key_does_not_contain_raw_token() -> None:
    key = _session_key("owner-secret-session")

    assert key.startswith("beachops:web-session:")
    assert "owner-secret-session" not in key


def test_passkey_enrollment_requires_telegram_owner_session() -> None:
    context = SimpleNamespace()

    with pytest.raises(HTTPException) as error:
        _require_owner_tma(context, None)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_session_principal_accepts_allowlisted_json_session() -> None:
    token = "opaque-token"
    context = SimpleNamespace(
        redis=FakeRedis(
            {
                _session_key(token): (
                    b'{"userId":42,"authMethod":"telegram_login","username":"owner"}'
                )
            }
        ),
        settings=SimpleNamespace(role_for=lambda user_id: Role.OPERATOR),
    )

    principal = await _session_principal(context, token)

    assert principal.user_id == 42
    assert principal.auth_method == "telegram_login"
    assert principal.username == "owner"


@pytest.mark.asyncio
async def test_session_principal_supports_legacy_owner_bytes() -> None:
    token = "opaque-token"
    context = SimpleNamespace(
        redis=FakeRedis({_session_key(token): b"42"}),
        settings=SimpleNamespace(role_for=lambda user_id: Role.OWNER),
    )

    principal = await _session_principal(context, token)

    assert principal.user_id == 42
    assert principal.auth_method == "passkey"


@pytest.mark.asyncio
async def test_registration_challenge_is_bound_to_owner() -> None:
    challenge_id = "challenge"
    redis = FakeRedis(
        {
            f"beachops:webauthn:challenge:{challenge_id}": (
                b'{"kind":"register","challenge":"YWJj","userId":42}'
            )
        }
    )
    context = SimpleNamespace(redis=redis)

    challenge = await _consume_challenge(
        context,
        challenge_id=challenge_id,
        kind="register",
        user_id=42,
    )

    assert challenge == b"abc"
    assert not redis.values
