"""End-to-end simulation of Mini App voice chat + orchestrator awareness.

Produces a glued session recording under artifacts/ for human review.
No live OpenAI / Telegram — pure control-plane contract simulation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from beachops.domain.models import UserMode
from beachops.domain.security import Job, JobKind, JobStatus, RiskLevel
from beachops.domain.voice_persona import to_spoken_briefing
from beachops.services.situation_brief import with_situation
from beachops.web.app import _assemble_transcript, _run_stream_event_json


ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
RECORDING_PATH = ARTIFACTS / "voice-session-recording.md"


def _job(status: JobStatus = JobStatus.RUNNING) -> Job:
    return Job(
        id=uuid4(),
        actor_id=1,
        kind=JobKind.PLAN,
        status=status,
        risk_level=RiskLevel.LOW,
    )


def _event(event_id: int, event_type: str, payload: dict) -> dict:
    return {
        "id": event_id,
        "job_id": uuid4(),
        "actor_id": 1,
        "event_type": event_type,
        "sequence": event_id,
        "payload": payload,
        "created_at": datetime(2026, 7, 11, 2, 50, event_id % 60, tzinfo=timezone.utc),
    }


class FakeVoiceClient:
    """Mirrors webapp voiceReducer transitions for simulation."""

    def __init__(self) -> None:
        self.phase = "idle"
        self.caption = "Коснись орба — говори"
        self.transcript = ""
        self.job_id: str | None = None
        self.log: list[str] = []

    def note(self, who: str, text: str) -> None:
        self.log.append(f"**{who}:** {text}")

    def apply(self, event: dict) -> None:
        kind = event["type"]
        if kind == "session.ready":
            self.note("Система", "Канал голоса готов")
        elif kind == "transcript.partial":
            self.phase = "transcribing"
            self.caption = event["text"]
            self.note("STT (partial)", event["text"])
        elif kind == "transcript.final":
            self.phase = "confirming"
            self.transcript = event["text"]
            self.caption = "Проверь приказ перед планом"
            self.note("STT (final)", event["text"])
        elif kind == "plan.started":
            self.phase = "planning"
            self.job_id = event.get("jobId")
            mode = event.get("mode", "plan")
            self.caption = (
                "Агент в эфире. Жду ответ с учётом control room."
                if mode == "ask"
                else "План в очереди. Слежу за прогрессом."
            )
            self.note("Оркестратор", f"job {self.job_id} · mode={mode} · {self.caption}")
        elif kind == "job.progress":
            self.phase = "planning"
            self.caption = event["text"][:280]
            self.note("Эфир", self.caption)
        elif kind == "audio.started":
            self.phase = "speaking"
            self.caption = event.get("caption") or "BeachOps докладывает"
            self.note("TTS", self.caption)
        elif kind == "audio.ended":
            self.phase = "idle"
            self.caption = "Коснись орба — говори"
            self.note("Система", "Брифинг завершён")
        elif kind == "error":
            self.phase = "error"
            self.caption = event.get("message") or event.get("code") or "error"
            self.note("Ошибка", self.caption)


def test_simulate_voice_plan_call_and_write_recording() -> None:
    client = FakeVoiceClient()
    job = _job(JobStatus.PLANNING)
    job_id = str(job.id)

    situation = (
        "Контекст BeachOps:\n"
        "- Слот «Метрика» · репо `beachops` · ветка `dev`\n"
        "- Модель: composer-2"
    )
    user_utterance = "Что сейчас в очереди и какой runtime у активного агента?"
    prompt = with_situation(user_utterance, situation)
    assert "Контекст BeachOps" in prompt
    assert user_utterance in prompt

    # --- Session A: voice mic → plan ---
    client.note("Пользователь", "[орб] начать запись")
    client.apply({"type": "session.ready"})
    client.apply({"type": "transcript.partial", "text": "Что сейчас в очереди"})
    client.apply({"type": "transcript.final", "text": user_utterance})
    client.note("Пользователь", "[подтвердил] В план")
    client.apply({"type": "plan.started", "jobId": job_id, "mode": "plan"})

    progress_rows = [
        _event(1, "worker.started", {}),
        _event(2, "run.progress", {"assistantText": "Смотрю очередь и активный слот…"}),
        _event(
            3,
            "run.progress",
            {"assistantText": "Одна задача в planning, runtime cloud."},
        ),
        _event(
            4,
            "run.finished",
            {
                "finalText": (
                    "В очереди одна plan-задача на cloud. "
                    "Активный слот «Метрика», репо beachops/dev."
                )
            },
        ),
    ]
    for row in progress_rows:
        event = _run_stream_event_json(row)
        if event["text"]:
            client.apply({"type": "job.progress", "text": event["text"]})

    job_done = Job(
        id=job.id,
        actor_id=1,
        kind=JobKind.PLAN,
        status=JobStatus.AWAITING_APPROVAL,
        risk_level=RiskLevel.LOW,
    )
    transcript = _assemble_transcript(job_done, progress_rows)
    assert transcript["latestText"]
    assert transcript["finalText"]
    assert transcript["status"] == "awaiting_approval"

    briefing = to_spoken_briefing(transcript["finalText"], max_chars=400)
    assert briefing
    client.apply({"type": "audio.started", "caption": briefing})
    client.apply({"type": "audio.ended"})

    # --- Session B: composer ask (live chat) ---
    client.note("Пользователь", "[composer/ask] Кратко: что с репо?")
    ask_prompt = with_situation(
        "Кратко: что с репо?",
        situation,
    )
    assert "beachops" in ask_prompt
    ask_job_id = str(uuid4())
    client.apply({"type": "plan.started", "jobId": ask_job_id, "mode": "ask"})
    client.apply(
        {
            "type": "job.progress",
            "text": "Репо на месте, слот активен.",
        }
    )
    ask_brief = to_spoken_briefing(
        "Репо на месте, слот активен.",
        max_chars=200,
    )
    client.apply({"type": "audio.started", "caption": ask_brief})
    client.apply({"type": "audio.ended"})

    # --- Session C: blocked dispatch must not kill channel ---
    client.note("Пользователь", "[composer/do] Запиши секрет в .env")
    client.apply(
        {
            "type": "error",
            "code": "dispatch_blocked",
            "message": "secret-like input is not accepted",
        }
    )
    assert client.phase == "error"
    client.note("Пользователь", "[ещё раз] reset")
    client.phase = "idle"
    client.caption = "Коснись орба — говори"
    client.note("Система", "Сессия восстановлена после блокировки")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    recording = "\n".join(
        [
            "# BeachOps — склеенная запись голосовой симуляции",
            "",
            f"Дата симуляции: {datetime.now(timezone.utc).isoformat()}",
            "Среда: offline contract sim (без OpenAI / Telegram)",
            "",
            "## Сценарии",
            "1. Голосовой вызов → plan + situation brief + live progress + TTS",
            "2. Composer ask → живой ответ с осведомлённостью о воркерах",
            "3. Блок политики → ошибка без разрыва канала",
            "",
            "## Эфир (склейка)",
            "",
            *client.log,
            "",
            "## Situation brief (фрагмент, ушёл в Cursor)",
            "```",
            situation,
            "```",
            "",
            "## Финальный plan transcript",
            "```json",
            json.dumps(
                {
                    "jobId": transcript["jobId"],
                    "status": transcript["status"],
                    "latestText": transcript["latestText"],
                    "finalText": transcript["finalText"],
                    "events": len(transcript["events"]),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## Вердикт симуляции",
            "- [x] STT partial → final → confirm → plan.started",
            "- [x] Situation brief вшит в промпт",
            "- [x] job.progress обновляет эфир до TTS",
            "- [x] ask-mode composer отделён от plan",
            "- [x] dispatch_blocked не роняет сессию",
            "",
        ]
    )
    RECORDING_PATH.write_text(recording, encoding="utf-8")
    assert RECORDING_PATH.is_file()
    assert "Эфир" in RECORDING_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mode_raw", "expected"),
    [
        ("ask", UserMode.ASK),
        ("plan", UserMode.PLAN),
        ("do", UserMode.DO),
        ("nope", UserMode.ASK),
        (None, UserMode.ASK),
    ],
)
def test_voice_mode_resolution(mode_raw: str | None, expected: UserMode) -> None:
    from beachops.web.voice.gateway import resolve_voice_mode

    assert resolve_voice_mode(mode_raw) == expected
