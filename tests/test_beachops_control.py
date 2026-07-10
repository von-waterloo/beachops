from __future__ import annotations

from beachops.domain.security import ApprovalKind, JobStatus
from beachops.services.inline_keyboards import job_approval_keyboard
from beachops.services.speech_service import _speech_safe
from beachops.services.stream_bridge import StreamState


def test_stream_redacts_secret_split_across_chunks() -> None:
    state = StreamState()
    state.append_assistant("Configuration: api_key=")
    state.append_assistant("super-secret-value")
    assert "super-secret-value" not in state.assistant_text
    assert "[REDACTED]" in state.assistant_text


def test_opaque_approval_callbacks_fit_telegram_limit() -> None:
    token = "a" * 43
    keyboard = job_approval_keyboard(
        approve_token=token,
        reject_token=token,
        revision_token=token,
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert all(value is not None and len(value.encode("utf-8")) <= 64 for value in callbacks)


def test_speech_output_hides_code_and_urls() -> None:
    safe = _speech_safe(
        "Готово. ```python\nprint('secret')\n``` https://github.com/private/repo"
    )
    assert "print" not in safe
    assert "github.com" not in safe
    assert "доступен на экране" in safe


def test_control_plane_contains_approval_states() -> None:
    assert JobStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert JobStatus.REVIEW_REQUIRED.value == "review_required"
    assert ApprovalKind.PLAN_EXECUTION.value == "plan_execution"
