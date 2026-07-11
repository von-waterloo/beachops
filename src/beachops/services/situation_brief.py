"""Situation brief for Cursor prompts.

Injected into ask/plan/do so the agent knows active slot / repo.
Voice channel gets a minimal brief without queue/worker chatter.
"""

from __future__ import annotations

from dataclasses import dataclass

from beachops.app_context import AppContext
from beachops.domain.security import JobStatus, Role
from beachops.services.agent_slots import RunContext


_ACTIVE = {
    JobStatus.QUEUED,
    JobStatus.PLANNING,
    JobStatus.APPROVED,
    JobStatus.RUNNING,
    JobStatus.AWAITING_APPROVAL,
    JobStatus.REVIEW_REQUIRED,
    JobStatus.REVISION_REQUESTED,
    JobStatus.PAUSED,
    JobStatus.BLOCKED,
}


@dataclass(frozen=True)
class ControlRoomCounts:
    running: int
    queued: int
    blocked: int
    pending_approvals: int
    workers_online: int


async def collect_control_room_counts(
    app: AppContext,
    *,
    actor_id: int,
    role: Role | None = None,
) -> ControlRoomCounts:
    """Fresh queue / approve counts for dashboard (not spoken aloud)."""
    resolved_role = role or app.settings.role_for(actor_id)
    jobs = (
        await app.jobs.list_all_internal(limit=40)
        if resolved_role == Role.OWNER
        else await app.jobs.list_for_actor(actor_id, limit=40)
    )
    active = [job for job in jobs if job.status in _ACTIVE]
    queued = sum(1 for job in active if job.status == JobStatus.QUEUED)
    running = sum(
        1
        for job in active
        if job.status in {JobStatus.RUNNING, JobStatus.PLANNING, JobStatus.APPROVED}
    )
    blocked = sum(
        1
        for job in active
        if job.status
        in {
            JobStatus.BLOCKED,
            JobStatus.AWAITING_APPROVAL,
            JobStatus.REVIEW_REQUIRED,
            JobStatus.PAUSED,
            JobStatus.REVISION_REQUESTED,
        }
    )
    approvals = (
        await app.approvals.list_pending(limit=20)
        if resolved_role == Role.OWNER
        else []
    )
    return ControlRoomCounts(
        running=running,
        queued=queued,
        blocked=blocked,
        pending_approvals=len(approvals),
        workers_online=0,
    )


def format_spoken_room(counts: ControlRoomCounts) -> str:
    """Spoken room bits disabled — voice stays conversational."""
    del counts
    return ""


async def build_spoken_room_bits(
    app: AppContext,
    *,
    actor_id: int,
    role: Role | None = None,
) -> str:
    """No-op for TTS; kept for call-site compatibility."""
    del app, actor_id, role
    return ""


async def build_situation_brief(
    app: AppContext,
    *,
    actor_id: int,
    run_context: RunContext | None = None,
    role: Role | None = None,
    channel: str | None = None,
) -> str:
    """Compact Russian status block for prompt injection."""
    voice = (channel or "").strip().lower() == "voice"
    model_key = await app.users.get_cursor_model_key(
        actor_id, default=app.settings.cursor_model
    )

    if voice:
        lines: list[str] = ["Контекст BeachOps:"]
        if run_context is not None:
            slot = run_context.slot
            repo = run_context.repo
            lines.append(
                f"- Слот «{slot.label}» · репо `{repo.alias}` · ветка `{repo.default_branch}`"
            )
        lines.append(f"- Модель: {model_key}")
        return "\n".join(lines)

    resolved_role = role or app.settings.role_for(actor_id)
    jobs = (
        await app.jobs.list_all_internal(limit=40)
        if resolved_role == Role.OWNER
        else await app.jobs.list_for_actor(actor_id, limit=40)
    )
    active = [job for job in jobs if job.status in _ACTIVE]
    queued = sum(1 for job in active if job.status == JobStatus.QUEUED)
    running = sum(
        1
        for job in active
        if job.status in {JobStatus.RUNNING, JobStatus.PLANNING, JobStatus.APPROVED}
    )
    blocked = sum(
        1
        for job in active
        if job.status
        in {
            JobStatus.BLOCKED,
            JobStatus.AWAITING_APPROVAL,
            JobStatus.REVIEW_REQUIRED,
            JobStatus.PAUSED,
            JobStatus.REVISION_REQUESTED,
        }
    )
    approvals = (
        await app.approvals.list_pending(limit=20)
        if resolved_role == Role.OWNER
        else []
    )

    lines = [
        "Ситуация BeachOps:",
        f"- Очередь: активно {running}, ждёт {queued}, блок/approve {blocked}",
    ]

    if run_context is not None:
        slot = run_context.slot
        repo = run_context.repo
        lines.append(
            f"- Активный слот: «{slot.label}»"
            f" · репо `{repo.alias}` · ветка `{repo.default_branch}`"
        )
        if slot.cursor_agent_id:
            lines.append(f"- Cursor agent: `{slot.cursor_agent_id}`")

    if approvals:
        lines.append(f"- Ждёт owner approve: {len(approvals)}")
        for item in approvals[:3]:
            lines.append(f"  · {item.kind.value} · job {str(item.job_id)[:8]}")

    if active:
        lines.append("- Живые задачи:")
        for job in active[:5]:
            title = (job.summary or job.kind.value)[:80]
            lines.append(f"  · {str(job.id)[:8]} · {job.status.value} · {title}")

    lines.append(f"- Модель Cursor: {model_key}")
    return "\n".join(lines)


def with_situation(prompt: str, situation: str | None) -> str:
    """Prepend situation brief to a user prompt when present."""
    body = (prompt or "").strip()
    brief = (situation or "").strip()
    if not brief:
        return body
    if not body:
        return brief
    return f"{brief}\n\n---\n\nЗапрос пользователя:\n{body}"
