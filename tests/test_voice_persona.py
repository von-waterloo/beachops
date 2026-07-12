from beachops.domain.voice_persona import (
    BEACHOPS_STT_PROMPT,
    MilestoneGate,
    SPARTAN_TTS_INSTRUCTIONS,
    milestone_line,
    spoken_ack,
    to_spoken_briefing,
)
from beachops.services.situation_brief import ControlRoomCounts, format_spoken_room


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


def test_spartan_instructions_are_conversational() -> None:
    lower = SPARTAN_TTS_INSTRUCTIONS.lower()
    assert "beach" in lower or "coworker" in lower or "conversational" in lower
    assert "war-room" not in lower and "war room" not in lower


def test_stt_prompt_biases_beachops_terms() -> None:
    assert "BeachOps" in BEACHOPS_STT_PROMPT
    assert "Cursor" in BEACHOPS_STT_PROMPT
    assert "Windows" not in BEACHOPS_STT_PROMPT
    assert "Keywords:" in BEACHOPS_STT_PROMPT


def test_spoken_ack_is_human_without_metrics() -> None:
    assert spoken_ack() == "Ок, беру."
    assert spoken_ack(runtime="cloud", room="В очереди ещё 1.") == "Ок, беру."
    assert "Windows" not in spoken_ack(runtime="windows")
    assert "Cloud" not in spoken_ack(runtime="cloud")


def test_milestone_line_only_approval() -> None:
    assert milestone_line(status="running", previous_status="queued") is None
    assert milestone_line(
        status="awaiting_approval", previous_status="running"
    ) == "План готов — глянь и скажи, делать или нет."
    assert milestone_line(progress_text="Agent started on cloud") is None
    assert milestone_line(progress_text="Writing file src/app.py") is None


def test_milestone_gate_interval_and_max() -> None:
    gate = MilestoneGate(min_interval_sec=15, max_per_job=2)
    assert gate.allow(0.0, "line a")
    gate.mark(0.0, "line a")
    assert not gate.allow(5.0, "line b")
    assert gate.allow(16.0, "line b")
    gate.mark(16.0, "line b")
    assert not gate.allow(40.0, "line c")


def test_format_spoken_room_silent() -> None:
    spoken = format_spoken_room(
        ControlRoomCounts(
            running=3,
            queued=2,
            blocked=1,
            pending_approvals=1,
            workers_online=2,
        )
    )
    assert spoken == ""
