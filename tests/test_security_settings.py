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


def test_agent_ssh_requires_all_three_fields() -> None:
    settings = _settings(owner=[1])
    assert not settings.agent_ssh_configured()
    assert settings.agent_ssh_cloud_env_vars() == {}

    settings = Settings.model_construct(
        tg_bot_token="t",
        cursor_api_key="c",
        openai_api_key="o",
        owner_user_ids=[1],
        agent_ssh_host="185.244.49.94",
        agent_ssh_user="const",
        agent_ssh_private_key_b64="",
    )
    assert not settings.agent_ssh_configured()


def test_agent_ssh_configured_and_env_vars() -> None:
    settings = Settings.model_construct(
        tg_bot_token="t",
        cursor_api_key="c",
        openai_api_key="o",
        owner_user_ids=[1],
        operator_user_ids=[2],
        agent_ssh_host="185.244.49.94",
        agent_ssh_port=22,
        agent_ssh_user="const",
        agent_ssh_private_key_b64="ZmFrZS1rZXk=",
        agent_ssh_remote_dir="",
    )
    assert settings.agent_ssh_configured()
    env = settings.agent_ssh_cloud_env_vars()
    assert env["AGENT_SSH_HOST"] == "185.244.49.94"
    assert env["AGENT_SSH_PORT"] == "22"
    assert env["AGENT_SSH_USER"] == "const"
    assert env["AGENT_SSH_PRIVATE_KEY_B64"] == "ZmFrZS1rZXk="
    assert "AGENT_SSH_REMOTE_DIR" not in env

    assert settings.can_use_server_ssh(1)
    assert settings.can_use_server_ssh(2)
    assert not settings.can_use_server_ssh(3)


def test_agent_ssh_remote_dir_included_when_set() -> None:
    settings = Settings.model_construct(
        tg_bot_token="t",
        cursor_api_key="c",
        openai_api_key="o",
        agent_ssh_host="h",
        agent_ssh_port=22,
        agent_ssh_user="u",
        agent_ssh_private_key_b64="k",
        agent_ssh_remote_dir="/home/const/tg-cursor-bot",
    )
    assert settings.agent_ssh_cloud_env_vars()["AGENT_SSH_REMOTE_DIR"] == "/home/const/tg-cursor-bot"

