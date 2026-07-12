from beachops.web.voice.gateway import (
    MIN_COMMIT_AUDIO_BYTES,
    build_voice_session_update,
    can_commit_audio_buffer,
)


def test_min_commit_is_100ms_pcm16_24k() -> None:
    assert MIN_COMMIT_AUDIO_BYTES == 4800


def test_resolve_voice_mode_defaults_to_ask() -> None:
    from beachops.web.voice.gateway import resolve_voice_mode
    from beachops.domain.models import UserMode

    assert resolve_voice_mode(None) is UserMode.ASK
    assert resolve_voice_mode("") is UserMode.ASK
    assert resolve_voice_mode("do") is UserMode.DO
    assert resolve_voice_mode("garbage") is UserMode.ASK


def test_can_commit_rejects_empty_and_short() -> None:
    assert not can_commit_audio_buffer(0)
    assert not can_commit_audio_buffer(4799)
    assert can_commit_audio_buffer(4800)
    assert can_commit_audio_buffer(24_000)


def test_session_update_for_gpt_realtime_is_realtime_not_transcription() -> None:
    payload = build_voice_session_update(
        model="gpt-realtime",
        transcription_model="gpt-4o-transcribe",
        language="ru",
    )
    assert payload["type"] == "realtime"
    assert payload["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert payload["audio"]["input"]["transcription"]["model"] == "gpt-4o-transcribe"
    assert payload["audio"]["input"]["transcription"]["language"] == "ru"
    assert payload["audio"]["input"]["turn_detection"] is None
    assert "noise_reduction" not in payload["audio"]["input"]


def test_session_update_for_whisper_uses_transcription_type() -> None:
    payload = build_voice_session_update(
        model="gpt-realtime-whisper",
        transcription_model="gpt-realtime-whisper",
        language="ru",
    )
    assert payload["type"] == "transcription"
    assert payload["audio"]["input"]["transcription"]["model"] == "gpt-realtime-whisper"
