from beachops.services.cursor_cloud_client import is_stream_expired_message


def test_is_stream_expired_message_cursor_wording() -> None:
    assert is_stream_expired_message("Run stream is no longer available")


def test_is_stream_expired_message_generic() -> None:
    assert is_stream_expired_message("stream expired")
    assert is_stream_expired_message("code=stream_expired")


def test_is_stream_expired_message_ignores_unrelated() -> None:
    assert not is_stream_expired_message("branch not found")
    assert not is_stream_expired_message("")
