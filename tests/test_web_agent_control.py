"""Tests for the Mini App agent-control endpoints' pure helpers and schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from beachops.domain.security import Job, JobKind, JobStatus, RiskLevel
from beachops.web.app import _assemble_transcript, _run_stream_event_json
from beachops.web.schemas import AgentUpdateRequest, PromptRequest


def _job(status: JobStatus = JobStatus.RUNNING) -> Job:
    return Job(
        id=uuid4(),
        actor_id=1,
        kind=JobKind.CHANGE,
        status=status,
        risk_level=RiskLevel.LOW,
    )


def _event_row(
    event_id: int,
    event_type: str,
    payload: dict,
) -> dict:
    return {
        "id": event_id,
        "job_id": uuid4(),
        "actor_id": 1,
        "event_type": event_type,
        "sequence": 0,
        "payload": payload,
        "created_at": datetime(2026, 7, 10, tzinfo=timezone.utc),
    }


def test_run_stream_event_json_prefers_final_over_assistant_over_text() -> None:
    row = _event_row(
        1,
        "run.progress",
        {"finalText": "final", "assistantText": "assistant", "text": "plain"},
    )
    event = _run_stream_event_json(row)
    assert event["text"] == "final"
    assert event["eventType"] == "run.progress"
    assert event["id"] == "1"

    row2 = _event_row(2, "worker.observation_done", {"text": "plain only"})
    assert _run_stream_event_json(row2)["text"] == "plain only"

    row3 = _event_row(3, "worker.claimed", {})
    assert _run_stream_event_json(row3)["text"] is None


def test_run_stream_event_json_decodes_json_string_payload() -> None:
    row = _event_row(4, "run.progress", {})
    row["payload"] = '{"assistantText": "hello"}'
    event = _run_stream_event_json(row)
    assert event["text"] == "hello"


def test_assemble_transcript_empty_events() -> None:
    job = _job(JobStatus.QUEUED)
    transcript = _assemble_transcript(job, [])
    assert transcript["jobId"] == str(job.id)
    assert transcript["status"] == "queued"
    assert transcript["events"] == []
    assert transcript["lastEventId"] == "0"
    assert transcript["latestText"] is None
    assert transcript["finalText"] is None


def test_assemble_transcript_tracks_latest_and_final_text() -> None:
    job = _job(JobStatus.SUCCEEDED)
    events = [
        _event_row(1, "worker.started", {}),
        _event_row(2, "run.progress", {"assistantText": "thinking..."}),
        _event_row(3, "run.progress", {"assistantText": "almost done"}),
        _event_row(4, "run.finished", {"finalText": "Done!"}),
    ]
    transcript = _assemble_transcript(job, events)
    assert transcript["status"] == "succeeded"
    assert len(transcript["events"]) == 4
    assert transcript["lastEventId"] == "4"
    assert transcript["latestText"] == "Done!"
    assert transcript["finalText"] == "Done!"


def test_assemble_transcript_latest_text_without_terminal_event() -> None:
    job = _job(JobStatus.RUNNING)
    events = [
        _event_row(1, "run.progress", {"assistantText": "step one"}),
        _event_row(2, "run.progress", {"assistantText": "step two"}),
    ]
    transcript = _assemble_transcript(job, events)
    assert transcript["latestText"] == "step two"
    assert transcript["finalText"] is None


def test_agent_update_request_accepts_partial_fields() -> None:
    body = AgentUpdateRequest(runtime="windows", localPath="C:/repo")
    assert body.runtime == "windows"
    assert body.localPath == "C:/repo"
    assert "preferredWorkerId" not in body.model_fields_set
    assert "runtime" in body.model_fields_set


def test_agent_update_request_rejects_unknown_runtime() -> None:
    with pytest.raises(ValidationError):
        AgentUpdateRequest(runtime="local")


def test_agent_update_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentUpdateRequest(runtime="cloud", extraField="nope")


def test_prompt_request_defaults_to_ask_mode() -> None:
    body = PromptRequest(prompt="hello")
    assert body.mode == "ask"
    assert body.slotId is None


def test_prompt_request_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="hello", mode="ask-nope")


def test_prompt_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="")
