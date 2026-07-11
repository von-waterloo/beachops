from beachops.domain.voice_persona import (
    BEACHOPS_STT_PROMPT,
    SPARTAN_TTS_INSTRUCTIONS,
    to_spoken_briefing,
)
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
