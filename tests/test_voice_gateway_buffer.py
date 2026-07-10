from beachops.web.voice.gateway import MIN_COMMIT_AUDIO_BYTES, can_commit_audio_buffer


def test_min_commit_is_100ms_pcm16_24k() -> None:
    assert MIN_COMMIT_AUDIO_BYTES == 4800


def test_can_commit_rejects_empty_and_short() -> None:
    assert not can_commit_audio_buffer(0)
    assert not can_commit_audio_buffer(4799)
    assert can_commit_audio_buffer(4800)
    assert can_commit_audio_buffer(24_000)
