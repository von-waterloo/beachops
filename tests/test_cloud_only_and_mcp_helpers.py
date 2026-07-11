from beachops.services.ops_ssh import parse_ops_ssh_hosts
from beachops.services.runtime_router import choose_runtime, resolve_runtime
from beachops.domain.runtime import AgentRuntime
from beachops.domain.prompts import build_prompt, VOICE_ASK_PREFIX
from beachops.domain.models import UserMode
from beachops.config.settings import Settings


def test_choose_runtime_always_cloud() -> None:
    assert choose_runtime(job_runtime="windows") == AgentRuntime.CLOUD
    assert resolve_runtime(slot_runtime="windows") == AgentRuntime.CLOUD


def test_parse_ops_ssh_hosts() -> None:
    hosts = parse_ops_ssh_hosts("eu=const@185.244.49.94,ru=root@80.78.253.176:22")
    assert set(hosts) == {"eu", "ru"}
    assert hosts["eu"].user == "const"
    assert hosts["eu"].host == "185.244.49.94"
    assert hosts["ru"].port == 22


def test_voice_prompt_prefix() -> None:
    text = build_prompt("как дела?", UserMode.ASK, channel="voice")
    assert text.startswith(VOICE_ASK_PREFIX)
    assert "как дела?" in text


def test_auto_approve_and_voice_milestone_defaults() -> None:
    settings = Settings.model_validate(
        {
            "TG_BOT_TOKEN": "t",
            "CURSOR_API_KEY": "c",
            "OPENAI_API_KEY": "o",
            "OWNER_USER_IDS": "1",
        }
    )
    assert settings.auto_approve_plans is False
    assert settings.voice_milestone_tts is False
