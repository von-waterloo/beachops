from beachops.domain.voice_persona import (
    BEACHOPS_STT_PROMPT,
    MilestoneGate,
    SPARTAN_TTS_INSTRUCTIONS,
    milestone_line,
    spoken_ack,
    to_spoken_briefing,
)
from beachops.services.situation_brief import ControlRoomCounts, format_spoken_room
from beachops.web.voice.gateway import RealtimeVoiceGateway


def test_spoken_briefing_strips_code_and_urls() -> None:
    raw = (
        "Готово.\n\n```python\nprint('x')\n```\n"
        "Смотри https://github.com/acme/app/pull/1 и файл `src/app.py`."
    )
    spoken = to_spoken_briefing(raw)
    assert "```" not in spoken
    assert "https://" not in spoken
    assert "Готово" in spoken
    assert "src/app.py" in spoken


def test_spoken_briefing_respects_max_chars_at_sentence() -> None:
    raw = "Первое предложение. " + ("Дальше много текста. " * 80)
    spoken = to_spoken_briefing(raw, max_chars=80)
    assert len(spoken) <= 81
    assert spoken.endswith(".")


def test_spartan_instructions_are_laconic() -> None:
    lower = SPARTAN_TTS_INSTRUCTIONS.lower()
    assert "laconic" in lower or "spartan" in lower or "calm" in lower
    assert "cheerfulness" in lower or "filler" in lower
    assert "war-room" not in lower and "war room" not in lower


def test_stt_prompt_biases_beachops_terms() -> None:
    assert "BeachOps" in BEACHOPS_STT_PROMPT
    assert "Cursor" in BEACHOPS_STT_PROMPT
    assert "Keywords:" in BEACHOPS_STT_PROMPT


def test_spoken_ack_mentions_runtime_and_room() -> None:
    assert spoken_ack(runtime="cloud") == "Взял. Cloud."
    assert "Windows" in spoken_ack(runtime="windows")
    assert "очереди" in spoken_ack(runtime="cloud", room="В очереди ещё 1.")


def test_milestone_line_status_whitelist() -> None:
    assert milestone_line(status="running", previous_status="queued") == "Агент в работе."
    assert milestone_line(
        status="awaiting_approval", previous_status="running"
    ) == "Ждёт вашего approve."
    assert milestone_line(status="queued", previous_status=None) is None
    assert milestone_line(status="succeeded", previous_status="running") is None
    assert milestone_line(status="running", previous_status="running") is None


def test_milestone_line_filters_noisy_progress() -> None:
    assert milestone_line(progress_text="thinking about the schema…") is None
    assert milestone_line(progress_text="Agent started on cloud") == "Агент на связи."
    assert milestone_line(progress_text="Writing file src/app.py") == "Правит код."


def test_milestone_gate_interval_and_max() -> None:
    gate = MilestoneGate(min_interval_sec=15, max_per_job=2)
    assert gate.allow(0.0, "Агент в работе.")
    gate.mark(0.0, "Агент в работе.")
    assert not gate.allow(5.0, "Строю план.")
    assert gate.allow(16.0, "Строю план.")
    gate.mark(16.0, "Строю план.")
    assert not gate.allow(40.0, "Нужен review.")  # max reached
    # Ack-style mark without counting
    gate2 = MilestoneGate(min_interval_sec=10, max_per_job=1)
    gate2.mark(0.0, "Взял.", count=False)
    assert gate2.count == 0
    assert not gate2.allow(5.0, "Агент в работе.")
    assert gate2.allow(11.0, "Агент в работе.")


def test_format_spoken_room_caps_bits() -> None:
    spoken = format_spoken_room(
        ControlRoomCounts(
            running=3,
            queued=2,
            blocked=1,
            pending_approvals=1,
            workers_online=2,
        )
    )
    assert "очереди" in spoken
    assert "approve" in spoken
    assert spoken.count(".") <= 3


def test_realtime_session_includes_stt_prompt() -> None:
    gateway = RealtimeVoiceGateway(api_key="sk-test")
    session = gateway._session_update_payload()
    assert session["type"] == "realtime"
    transcription = session["audio"]["input"]["transcription"]
    assert transcription["model"] == "gpt-4o-transcribe"
    assert transcription["prompt"] == BEACHOPS_STT_PROMPT
    assert "delay" not in transcription


def test_whisper_nested_model_skips_prompt() -> None:
    gateway = RealtimeVoiceGateway(
        api_key="sk-test",
        input_transcribe_model="whisper-1",
    )
    transcription = gateway._session_update_payload()["audio"]["input"]["transcription"]
    assert "prompt" not in transcription
