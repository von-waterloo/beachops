"""RBAC settings compatibility and precedence."""

import pytest

from beachops.config.settings import Settings
from beachops.domain.models import UserMode
from beachops.domain.security import Role
from beachops.services.authz import AuthorizationError, require_owner


def _settings(**roles: list[int]) -> Settings:
    return Settings.model_construct(
        tg_bot_token="t",
        cursor_api_key="c",
        openai_api_key="o",
        whitelist_user_ids=roles.get("whitelist", []),
        admin_user_ids=roles.get("admin", []),
        viewer_user_ids=roles.get("viewer", []),
        operator_user_ids=roles.get("operator", []),
        owner_user_ids=roles.get("owner", []),
    )


def test_explicit_role_precedence() -> None:
    settings = _settings(
        viewer=[1, 2, 3],
        operator=[2, 3],
        owner=[3],
    )

    assert settings.role_for(1) == Role.VIEWER
    assert settings.role_for(2) == Role.OPERATOR
    assert settings.role_for(3) == Role.OWNER
    assert settings.role_for(4) is None


def test_explicit_role_env_lists_are_parsed() -> None:
    settings = Settings.model_validate(
        {
            "TG_BOT_TOKEN": "t",
            "CURSOR_API_KEY": "c",
            "OPENAI_API_KEY": "o",
            "VIEWER_USER_IDS": "1, 2",
            "OPERATOR_USER_IDS": "2, 3",
            "OWNER_USER_IDS": "3",
        }
    )

    assert settings.viewer_user_ids == [1, 2]
    assert settings.operator_user_ids == [2, 3]
    assert settings.owner_user_ids == [3]
    assert settings.role_for(3) == Role.OWNER


def test_legacy_lists_remain_compatible() -> None:
    settings = _settings(whitelist=[10, 11], admin=[11])

    assert settings.role_for(10) == Role.VIEWER
    assert settings.role_for(11) == Role.OWNER
    assert settings.is_whitelisted(10)
    assert settings.is_admin(11)


def test_operator_can_write_but_cannot_approve() -> None:
    settings = _settings(operator=[20], owner=[30])

    assert settings.can_use_mode(20, UserMode.DO)
    assert settings.can_use_mode(20, UserMode.PLAN)
    assert not settings.can_approve(20)
    assert settings.can_approve(30)


def test_owner_only_control_actions() -> None:
    with pytest.raises(AuthorizationError):
        require_owner(Role.OPERATOR)

    require_owner(Role.OWNER)

