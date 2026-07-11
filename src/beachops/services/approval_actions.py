"""Shared owner decisions for Telegram and Mini App."""

from __future__ import annotations

from uuid import uuid4

from beachops.app_context import AppContext
from beachops.domain.models import UserMode
from beachops.domain.security import ApprovalKind, JobKind, JobStatus, RiskLevel


async def approve_job(app: AppContext, job, kind: ApprovalKind) -> dict:
    if kind == ApprovalKind.RESULT_REVIEW:
        await app.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[JobStatus.REVIEW_REQUIRED],
            to_status=JobStatus.ACCEPTED,
            event_type="review.accepted",
        )
        return {"status": "accepted", "job_id": job.id, "merged": False}

    app.repository_policy.require_allowed(
        job.repository_url or "",
        job.branch or "",
        write=True,
    )
    source = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
    payload = app.payload_crypto.encrypt_json(
        {
            **source,
            "prompt": "Выполни одобренный план. Не выходи за его рамки.",
            "mode": UserMode.DO.value,
            "approved_plan_job_id": str(job.id),
        }
    )
    change_job = await app.jobs.create(
        job.actor_id,
        kind=JobKind.CHANGE,
        risk_level=RiskLevel.MEDIUM,
        status=JobStatus.APPROVED,
        repository_url=job.repository_url,
        branch=job.branch,
        summary=f"Выполнение одобренного плана {job.id}",
        payload_ciphertext=payload,
        telegram_chat_id=job.telegram_chat_id,
        idempotency_key=f"approval:{job.id}",
    )
    await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[JobStatus.AWAITING_APPROVAL],
        to_status=JobStatus.APPROVED,
        event_type="approval.approved",
    )
    await app.arq.enqueue_job("execute_job", str(change_job.id))
    return {"status": "approved", "job_id": change_job.id}


async def reject_job(app: AppContext, job) -> None:
    await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[JobStatus.AWAITING_APPROVAL, JobStatus.REVIEW_REQUIRED],
        to_status=JobStatus.REJECTED,
        event_type="approval.rejected",
    )


async def request_revision(app: AppContext, job, revision: str) -> dict:
    assessment = app.risk_policy.assess(
        revision,
        job_kind=JobKind.CHANGE,
        branch=job.branch,
        write=True,
    )
    if assessment.blocked or assessment.level == RiskLevel.HIGH:
        raise PermissionError(
            ", ".join(assessment.reasons) or "revision blocked by policy"
        )
    source = app.payload_crypto.decrypt_json(job.payload_ciphertext or "")
    payload = app.payload_crypto.encrypt_json(
        {
            **source,
            "prompt": revision,
            "mode": UserMode.DO.value,
            "approved_plan_job_id": str(job.id),
        }
    )
    revision_job = await app.jobs.create(
        job.actor_id,
        kind=JobKind.CHANGE,
        risk_level=RiskLevel.MEDIUM,
        status=JobStatus.REVISION_REQUESTED,
        repository_url=job.repository_url,
        branch=job.branch,
        summary=f"Доработка результата {job.id}",
        payload_ciphertext=payload,
        telegram_chat_id=job.telegram_chat_id,
        idempotency_key=f"revision:{job.id}:{uuid4()}",
    )
    await app.jobs.transition(
        job.actor_id,
        job.id,
        from_statuses=[JobStatus.REVIEW_REQUIRED],
        to_status=JobStatus.REVISION_REQUESTED,
        event_type="review.revision_requested",
    )
    await app.arq.enqueue_job("execute_job", str(revision_job.id))
    return {"status": "revision_requested", "job_id": revision_job.id}
