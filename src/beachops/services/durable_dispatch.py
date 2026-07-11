"""Create encrypted durable jobs and enqueue only policy-approved work."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.domain.runtime import AgentRuntime
from beachops.domain.security import Job, JobKind, JobStatus, RiskLevel
from beachops.services.agent_slots import RunContext
from beachops.services.redaction import redact_text
from beachops.services.repository_policy import RepositoryNotAllowedError
from beachops.services.runtime_router import choose_runtime


@dataclass(frozen=True)
class DispatchResult:
    job: Job
    enqueued: bool
    reason: str | None = None


def _job_kind(mode: UserMode) -> JobKind:
    if mode == UserMode.ASK:
        return JobKind.READ
    if mode == UserMode.PLAN:
        return JobKind.PLAN
    return JobKind.CHANGE


async def dispatch_prompt(
    app: AppContext,
    *,
    actor_id: int,
    prompt: str,
    mode: UserMode,
    run_context: RunContext,
    idempotency_key: str | None = None,
    approved_plan_job_id: UUID | None = None,
    display_summary: str | None = None,
) -> DispatchResult:
    kind = _job_kind(mode)
    repo = run_context.repo
    write = kind == JobKind.CHANGE
    # Secret scan the full prompt (may include situation brief).
    redacted_prompt = redact_text(prompt).strip()
    # UI/job chip title: prefer the raw user utterance over injected brief.
    safe_summary = redact_text((display_summary or prompt)).strip()

    if redacted_prompt != prompt.strip():
        job = await app.jobs.create(
            actor_id,
            kind=kind,
            risk_level=RiskLevel.BLOCKED,
            status=JobStatus.BLOCKED,
            repository_url=repo.github_url,
            branch=repo.default_branch,
            summary="Запрос содержит данные, похожие на секрет.",
            idempotency_key=idempotency_key,
        )
        return DispatchResult(job, False, "secret-like input is not accepted")

    try:
        app.repository_policy.require_allowed(
            repo.github_url,
            repo.default_branch,
            write=write,
        )
    except RepositoryNotAllowedError as exc:
        job = await app.jobs.create(
            actor_id,
            kind=kind,
            risk_level=RiskLevel.BLOCKED,
            status=JobStatus.BLOCKED,
            repository_url=repo.github_url,
            branch=repo.default_branch,
            summary=safe_summary[:300],
            idempotency_key=idempotency_key,
        )
        return DispatchResult(job, False, str(exc))

    assessment = app.risk_policy.assess(
        prompt,
        job_kind=kind,
        branch=repo.default_branch,
        write=write,
    )
    if assessment.blocked or assessment.level == RiskLevel.HIGH:
        job = await app.jobs.create(
            actor_id,
            kind=kind,
            risk_level=assessment.level,
            status=JobStatus.BLOCKED,
            repository_url=repo.github_url,
            branch=repo.default_branch,
            summary=safe_summary[:300],
            idempotency_key=idempotency_key,
        )
        reason = ", ".join(assessment.reasons) or "blocked by policy"
        return DispatchResult(job, False, reason)

    runtime = choose_runtime(slot=run_context.slot)
    payload = app.payload_crypto.encrypt_json(
        {
            "prompt": prompt,
            "mode": mode.value,
            "slot_id": run_context.slot.id,
            "repo_id": repo.id,
            "runtime": runtime.value,
            "local_path": run_context.slot.local_path,
            "approved_plan_job_id": (
                str(approved_plan_job_id) if approved_plan_job_id else None
            ),
        }
    )
    job = await app.jobs.create(
        actor_id,
        kind=kind,
        risk_level=assessment.level,
        status=JobStatus.QUEUED,
        repository_url=repo.github_url,
        branch=repo.default_branch,
        summary=safe_summary[:300],
        payload_ciphertext=payload,
        telegram_chat_id=actor_id,
        idempotency_key=idempotency_key,
        runtime=runtime.value,
    )
    # Windows jobs are claimed by the outbound Windows worker, not ARQ.
    if runtime != AgentRuntime.WINDOWS:
        await app.arq.enqueue_job(
            "execute_job",
            str(job.id),
            _job_id=f"beachops:job:{job.id}",
        )
    return DispatchResult(job, True)
