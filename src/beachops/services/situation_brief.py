"""Control-room situation brief for Cursor / voice orchestrator awareness.

Injected into ask/plan/do prompts so the agent knows queue, active
jobs, approvals, workers, and the active slot — not only the latest utterance.
"""

from __future__ import annotations

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


async def build_situation_brief(
    app: AppContext,
    *,
    actor_id: int,
    run_context: RunContext | None = None,
    role: Role | None = None,
) -> str:
    """Compact Russian status block for prompt injection (Telegram-friendly)."""
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
    workers = await app.worker_nodes.list_online()

    lines: list[str] = [
        "Ситуация BeachOps (control room — учитывай при ответе):",
        f"- Очередь: активно {running}, ждёт {queued}, блок/approve {blocked}",
    ]

    if run_context is not None:
        slot = run_context.slot
        repo = run_context.repo
        runtime = slot.runtime or "cloud"
        lines.append(
            f"- Активный слот: «{slot.label}» · {runtime}"
            f" · репо `{repo.alias}` · ветка `{repo.default_branch}`"
        )
        if runtime == "windows" and slot.local_path:
            lines.append(f"- Windows path: `{slot.local_path}`")
        if slot.cursor_agent_id:
            lines.append(f"- Cursor agent: `{slot.cursor_agent_id}`")

    if workers:
        hostnames = ", ".join(node["hostname"] for node in workers[:5])
        lines.append(f"- Windows-воркеры онлайн: {hostnames}")
    else:
        lines.append("- Windows-воркеры: нет онлайн")

    if approvals:
        lines.append(f"- Ждёт owner approve: {len(approvals)}")
        for item in approvals[:3]:
            lines.append(f"  · {item.kind.value} · job {str(item.job_id)[:8]}")

    if active:
        lines.append("- Живые задачи:")
        for job in active[:5]:
            title = (job.summary or job.kind.value)[:80]
            runtime = job.runtime or "cloud"
            lines.append(
                f"  · {str(job.id)[:8]} · {job.status.value} · {runtime} · {title}"
            )

    model_key = await app.users.get_cursor_model_key(
        actor_id, default=app.settings.cursor_model
    )
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
