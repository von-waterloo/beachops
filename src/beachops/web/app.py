"""FastAPI control plane for the authenticated BeachOps Mini App."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from beachops.app_context import AppContext
from beachops.config.settings import Settings, get_settings
from beachops.domain.cursor_models import (
    CURSOR_MODEL_ORDER,
    CursorModelKey,
    cursor_model_label,
    normalize_cursor_model_key,
)
from beachops.domain.models import UserMode
from beachops.domain.runtime import cursor_agent_url
from beachops.domain.security import (
    ApprovalDecision,
    ApprovalKind,
    JobKind,
    JobStatus,
    Role,
)
from beachops.services.approval_actions import approve_job, reject_job, request_revision
from beachops.services.durable_dispatch import dispatch_prompt
from beachops.services.logging_config import (
    bind_log_context,
    clear_log_context,
    configure_logging,
    new_correlation_id,
)
from beachops.web.passkey_auth import (
    resolve_request_principal,
    resolve_websocket_principal,
    router as passkey_auth_router,
)
from beachops.web.schemas import (
    DecisionRequest,
    DeployDispatchRequest,
    PanicRequest,
    RepoCreateRequest,
    RepoUpdateRequest,
)
from beachops.web.telegram_auth import (
    TelegramInitDataError,
    TelegramPrincipal,
    extract_tma_authorization,
    validate_init_data,
)
from beachops.web.voice import RealtimeVoiceGateway, VoiceGatewayLimits

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, service="api")
    context = await AppContext.create(settings)
    app.state.context = context
    try:
        yield
    finally:
        await context.close()


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)
        correlation_id = new_correlation_id()
        started = time.monotonic()
        bind_log_context(
            correlation_id=correlation_id,
            action="http_request",
            service="api",
        )
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-Id"] = correlation_id
            return response
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                status_code,
                extra={"duration_ms": duration_ms, "correlation_id": correlation_id},
            )
            clear_log_context()
            bind_log_context(service="api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="BeachOps API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.add_middleware(RequestLogMiddleware)
    app.include_router(passkey_auth_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, str]:
        context = _context(request)
        await context.pool.fetchval("SELECT 1")
        await context.redis.ping()
        return {"status": "ready"}

    @app.get("/api/me")
    async def me(
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> dict:
        context = _context(request)
        role = context.settings.role_for(principal.user_id)
        model_key = await context.users.get_cursor_model_key(
            principal.user_id, default=context.settings.cursor_model
        )
        return {
            "userId": principal.user_id,
            "role": role.value if role else "none",
            "writesEnabled": not await context.system_state.is_panic_enabled(),
            "authMethod": principal.auth_method,
            "hasPasskey": await context.passkeys.has_any(principal.user_id),
            "cursorModelKey": model_key,
            "models": [
                {"key": choice.value, "label": cursor_model_label(choice.value)}
                for choice in CURSOR_MODEL_ORDER
            ],
        }

    @app.put("/api/me/model")
    async def set_model(
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> dict:
        context = _context(request)
        body = await request.json()
        raw_key = str(body.get("modelKey") or body.get("model_key") or "").strip()
        model_key = normalize_cursor_model_key(
            raw_key, default=context.settings.cursor_model
        )
        if model_key not in {item.value for item in CursorModelKey}:
            raise HTTPException(status_code=400, detail="unknown model")
        await context.users.set_cursor_model_key(principal.user_id, model_key)
        logger.info(
            "Cursor model updated",
            extra={
                "user_id": principal.user_id,
                "action": "set_model",
            },
        )
        return {
            "cursorModelKey": model_key,
            "label": cursor_model_label(model_key),
        }

    @app.get("/api/dashboard")
    async def dashboard(
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> dict:
        context = _context(request)
        role = context.settings.role_for(principal.user_id)
        cache_scope = (
            f"owner:{principal.user_id}"
            if role == Role.OWNER
            else f"actor:{principal.user_id}"
        )
        cached = await context.hot_cache.get_dashboard(cache_scope)
        if cached is not None:
            return cached

        jobs = (
            await context.jobs.list_all_internal(limit=100)
            if role == Role.OWNER
            else await context.jobs.list_for_actor(principal.user_id, limit=100)
        )
        approvals = (
            await context.approvals.list_pending(limit=100)
            if role == Role.OWNER
            else []
        )
        approval_payload = []
        for item in approvals:
            job = await context.jobs.get_internal(item.job_id)
            approval_payload.append(_approval_json(item, job=job))
        events = await _recent_events(context, principal.user_id, role)
        total_tokens = sum(job.total_tokens or 0 for job in jobs)
        user_repos = await context.repos.list_repos(principal.user_id)
        slots = await context.agent_slots.list_slots(principal.user_id)
        self_improve_url = context.settings.self_improve_repo_normalized()
        snapshot = {
            "jobs": [_job_json(job) for job in jobs],
            "events": events,
            "approvals": approval_payload,
            "repositories": [_repo_json(repo) for repo in user_repos],
            "agents": [_agent_slot_json(slot) for slot in slots],
            "usage": {
                "period": "current",
                "voiceMinutes": 0,
                "jobs": len(jobs),
                "limitPercent": 0,
                "totalTokens": total_tokens,
            },
            "panic": await context.system_state.is_panic_enabled(),
            "role": role.value if role else "none",
            "defaultBranch": context.settings.default_branch,
            "workers": [
                _worker_json(node)
                for node in await context.worker_nodes.list_online()
            ],
            "queue": _queue_stats(jobs),
            "selfImprove": {
                "enabled": bool(context.settings.self_improve_enabled and self_improve_url),
                "repoUrl": self_improve_url,
                "branches": list(context.settings.self_improve_branches),
            },
        }
        await context.hot_cache.set_dashboard(cache_scope, snapshot)
        return snapshot

    @app.post("/api/repos")
    async def create_repo(
        body: RepoCreateRequest,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> dict:
        context = _context(request)
        role = context.settings.role_for(principal.user_id)
        if role not in {Role.OPERATOR, Role.OWNER}:
            raise HTTPException(status_code=403, detail="operator role required")
        from beachops.services.repo_parse import (
            MAX_ALIAS_LEN,
            alias_from_github_url,
            normalize_github_repo_url,
        )
        from beachops.services.repository_policy import (
            RepositoryNotAllowedError,
            RepositoryPolicyError,
            normalize_github_url,
        )

        branch = (body.branch or context.settings.default_branch).strip() or "dev"
        try:
            github_url = normalize_github_url(normalize_github_repo_url(body.url))
            context.repository_policy.require_allowed(
                github_url, branch, write=False
            )
        except (RepositoryNotAllowedError, RepositoryPolicyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        alias = (body.alias or alias_from_github_url(github_url)).strip()[:MAX_ALIAS_LEN]
        if not alias:
            raise HTTPException(status_code=400, detail="alias is required")
        existing = await context.repos.list_repos(principal.user_id)
        make_active = body.makeActive or not existing
        repo = await context.repos.add_repo(
            principal.user_id,
            alias=alias,
            github_url=github_url,
            default_branch=branch,
            make_active=make_active,
        )
        if make_active:
            await context.agent_slots.sync_active_slot_repo(principal.user_id, repo)
        return _repo_json(repo)

    @app.patch("/api/repos/{repo_id}")
    async def update_repo(
        repo_id: int,
        body: RepoUpdateRequest,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> dict:
        context = _context(request)
        role = context.settings.role_for(principal.user_id)
        if role not in {Role.OPERATOR, Role.OWNER}:
            raise HTTPException(status_code=403, detail="operator role required")
        from beachops.services.repository_policy import (
            RepositoryNotAllowedError,
            RepositoryPolicyError,
        )

        current = await context.repos.get_by_id(principal.user_id, repo_id)
        if current is None:
            raise HTTPException(status_code=404, detail="repository not found")
        branch = body.branch.strip() if body.branch else None
        if branch:
            try:
                context.repository_policy.require_allowed(
                    current.github_url, branch, write=False
                )
            except (RepositoryNotAllowedError, RepositoryPolicyError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        repo = await context.repos.update_repo(
            principal.user_id,
            repo_id,
            default_branch=branch,
            make_active=body.makeActive,
        )
        if repo is None:
            raise HTTPException(status_code=404, detail="repository not found")
        if repo.is_active:
            await context.agent_slots.sync_active_slot_repo(principal.user_id, repo)
        return _repo_json(repo)

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(
        job_id: UUID,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> list[dict]:
        context = _context(request)
        job = await context.jobs.get(principal.user_id, job_id)
        if job is None and context.settings.role_for(principal.user_id) != Role.OWNER:
            raise HTTPException(status_code=404, detail="job not found")
        if job is None:
            internal = await context.jobs.get_internal(job_id)
            if internal is None:
                raise HTTPException(status_code=404, detail="job not found")
            actor_id = internal.actor_id
        else:
            actor_id = principal.user_id
        events = await context.jobs.list_events(actor_id, job_id)
        return [
            {
                "id": str(item["id"]),
                "kind": item["event_type"],
                "summary": str(item.get("to_status") or item["event_type"]),
                "createdAt": item["created_at"].isoformat(),
                "jobId": str(job_id),
            }
            for item in events
        ]

    @app.post("/api/approvals/{approval_id}/decision")
    async def decide_approval(
        approval_id: UUID,
        body: DecisionRequest,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        context = _context(request)
        role = context.settings.role_for(principal.user_id)
        if role != Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        if not idempotency_key or not await context.idempotency.claim(
            "approval", idempotency_key, ttl_sec=3600
        ):
            raise HTTPException(status_code=409, detail="duplicate or missing idempotency key")

        approval = await context.approvals.get_internal(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        job = await context.jobs.get_internal(approval.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if (
            body.decision == "approve"
            and approval.kind == ApprovalKind.PLAN_EXECUTION
            and await context.system_state.is_panic_enabled()
        ):
            raise HTTPException(status_code=409, detail="write actions disabled by panic")

        if body.decision == "approve":
            decided = await context.approvals.decide(
                approval.actor_id,
                approval.id,
                decided_by=principal.user_id,
                decider_role=Role.OWNER,
                decision=ApprovalDecision.APPROVED,
            )
            if decided is None:
                raise HTTPException(status_code=409, detail="approval expired or consumed")
            try:
                result = await approve_job(context, job, approval.kind)
            except PermissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        elif body.decision == "revision":
            if approval.kind != ApprovalKind.RESULT_REVIEW or not body.revision:
                raise HTTPException(status_code=400, detail="revision text required")
            await context.approvals.decide(
                approval.actor_id,
                approval.id,
                decided_by=principal.user_id,
                decider_role=Role.OWNER,
                decision=ApprovalDecision.REJECTED,
                reason="revision requested",
            )
            try:
                result = await request_revision(context, job, body.revision)
            except PermissionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            await context.approvals.decide(
                approval.actor_id,
                approval.id,
                decided_by=principal.user_id,
                decider_role=Role.OWNER,
                decision=ApprovalDecision.REJECTED,
            )
            await reject_job(context, job)
            result = {"status": "rejected", "jobId": str(job.id)}
        await context.hot_cache.bump_dashboard_generation()
        return result

    @app.post("/api/panic")
    async def panic(
        body: PanicRequest,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        context = _context(request)
        if context.settings.role_for(principal.user_id) != Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        if not idempotency_key or not await context.idempotency.claim(
            "panic", idempotency_key, ttl_sec=3600
        ):
            raise HTTPException(status_code=409, detail="duplicate or missing idempotency key")
        await context.system_state.set_panic(
            body.enabled,
            actor_id=principal.user_id,
            actor_role=Role.OWNER,
        )
        if body.enabled:
            await _cancel_write_jobs(context)
        await context.audit.append(
            actor_id=principal.user_id,
            event_type="system.panic",
            action="enable" if body.enabled else "disable",
            outcome="success",
            details={},
        )
        return {"panic": body.enabled}

    @app.post("/api/deploy/dispatch")
    async def deploy_dispatch(
        body: DeployDispatchRequest,
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        context = _context(request)
        if context.settings.role_for(principal.user_id) != Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        if not context.settings.github_deploy_dispatch:
            raise HTTPException(status_code=409, detail="deploy dispatch disabled")
        if not idempotency_key or not await context.idempotency.claim(
            "deploy", idempotency_key, ttl_sec=3600
        ):
            raise HTTPException(status_code=409, detail="duplicate or missing idempotency key")
        from beachops.services.deploy_trigger import (
            DeployTriggerError,
            trigger_prod_deploy,
        )

        try:
            result = await trigger_prod_deploy(
                token=context.settings.github_token,
                repository=context.settings.github_repo,
                sha=body.sha,
                workflow=context.settings.github_deploy_workflow,
                ref=body.ref or context.settings.github_deploy_ref,
            )
        except DeployTriggerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await context.audit.append(
            actor_id=principal.user_id,
            event_type="deploy.dispatch",
            action="workflow_dispatch",
            outcome="success",
            details={"sha": result.sha, "ref": result.ref},
        )
        await context.deploy_history.record(
            sha=result.sha,
            ref=result.ref,
            reason="deploy",
        )
        return {
            "repository": result.repository,
            "workflow": result.workflow,
            "ref": result.ref,
            "sha": result.sha,
        }

    @app.websocket("/api/voice/ws")
    async def voice(websocket: WebSocket) -> None:
        await websocket.accept()
        context: AppContext = websocket.app.state.context
        correlation_id = new_correlation_id()
        session_started = time.monotonic()
        bind_log_context(
            correlation_id=correlation_id,
            action="voice_session",
            service="api",
        )
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            authorization = str(auth_message.get("authorization", ""))
            principal = await resolve_websocket_principal(websocket, authorization)
        except (TelegramInitDataError, asyncio.TimeoutError, ValueError):
            logger.warning(
                "Voice WS auth failed",
                extra={"action": "voice_auth", "error_code": "4401"},
            )
            await websocket.close(code=4401)
            clear_log_context()
            bind_log_context(service="api")
            return

        bind_log_context(user_id=principal.user_id)
        limit = await context.rate_limiter.check(
            subject=str(principal.user_id),
            action="voice_session",
            limit=5,
            window_sec=60,
        )
        if not limit.allowed:
            logger.warning(
                "Voice WS rate limited",
                extra={
                    "user_id": principal.user_id,
                    "action": "voice_session",
                    "error_code": "4429",
                },
            )
            await websocket.close(code=4429)
            clear_log_context()
            bind_log_context(service="api")
            return

        logger.info(
            "Voice WS session ready",
            extra={"user_id": principal.user_id, "action": "voice_session"},
        )
        await websocket.send_json({"type": "session.ready"})

        gateway = RealtimeVoiceGateway(
            api_key=context.settings.openai_api_key,
            model=context.settings.voice_realtime_model,
            input_transcribe_model=context.settings.voice_input_transcribe_model,
            limits=VoiceGatewayLimits(
                max_session_bytes=24_000
                * 2
                * context.settings.voice_max_session_sec
            ),
        )
        result_tasks: set[asyncio.Task] = set()

        async def on_plan_request(transcript: str) -> str:
            run_context = await context.agent_slots.get_run_context(principal.user_id)
            if run_context is None:
                logger.warning(
                    "Voice plan blocked: no repository",
                    extra={
                        "user_id": principal.user_id,
                        "action": "voice_plan_request",
                        "error_code": "no_repository",
                    },
                )
                raise ValueError("repository is not selected")
            dispatched = await dispatch_prompt(
                context,
                actor_id=principal.user_id,
                prompt=transcript,
                mode=UserMode.PLAN,
                run_context=run_context,
                idempotency_key=f"voice:{principal.user_id}:{uuid4()}",
            )
            if not dispatched.enqueued:
                logger.warning(
                    "Voice plan blocked: %s",
                    dispatched.reason or "request blocked",
                    extra={
                        "user_id": principal.user_id,
                        "action": "voice_plan_request",
                        "error_code": "dispatch_blocked",
                    },
                )
                raise ValueError(dispatched.reason or "request blocked")
            bind_log_context(job_id=str(dispatched.job.id))
            logger.info(
                "Voice plan enqueued",
                extra={
                    "user_id": principal.user_id,
                    "job_id": str(dispatched.job.id),
                    "action": "voice_plan_request",
                },
            )
            task = asyncio.create_task(
                _speak_job_result(context, websocket, dispatched.job.id)
            )
            result_tasks.add(task)
            task.add_done_callback(result_tasks.discard)
            return str(dispatched.job.id)

        try:
            await gateway.run(websocket, on_plan_request=on_plan_request)
        except Exception:
            logger.exception(
                "Voice WS gateway failed",
                extra={
                    "user_id": principal.user_id,
                    "action": "voice_session",
                    "error_code": "provider_unavailable",
                },
            )
            with suppress(Exception):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "provider_unavailable",
                        "message": "Voice service unavailable",
                    }
                )
            with suppress(Exception):
                await websocket.close(code=1011)
        finally:
            for task in result_tasks:
                task.cancel()
            logger.info(
                "Voice WS session closed",
                extra={
                    "user_id": principal.user_id,
                    "action": "voice_session",
                    "duration_ms": int((time.monotonic() - session_started) * 1000),
                },
            )
            clear_log_context()
            bind_log_context(service="api")

    @app.post("/api/workers/register")
    async def register_worker(request: Request) -> dict:
        context = _context(request)
        body = await request.json()
        enrolled_by = await _authorize_worker_register(request, context)
        hostname = str(body.get("hostname") or "").strip()
        if not hostname:
            raise HTTPException(status_code=400, detail="hostname required")
        platform = str(body.get("platform") or "windows").strip() or "windows"
        capabilities = body.get("capabilities") or {}
        if not isinstance(capabilities, dict):
            raise HTTPException(status_code=400, detail="capabilities must be an object")

        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_worker_token(raw_token)
        node = await context.worker_nodes.register(
            hostname=hostname,
            token_hash=token_hash,
            capabilities=capabilities,
            platform=platform,
            enrolled_by=enrolled_by,
        )
        await context.audit.append(
            actor_id=enrolled_by,
            event_type="worker.register",
            action="register",
            outcome="success",
            details={"nodeId": str(node["id"]), "hostname": hostname},
        )
        return {
            "id": str(node["id"]),
            "hostname": node["hostname"],
            "platform": node["platform"],
            "status": node["status"],
            "token": raw_token,
        }

    @app.post("/api/workers/heartbeat")
    async def worker_heartbeat(request: Request) -> dict:
        context = _context(request)
        node = await _current_worker_node(request, context)
        body = await request.json()
        hostname = str(body.get("hostname") or node["hostname"])
        capabilities = body.get("capabilities") or {}
        if not isinstance(capabilities, dict):
            raise HTTPException(status_code=400, detail="capabilities must be an object")
        updated = await context.worker_nodes.upsert_heartbeat(
            node["id"],
            hostname=hostname,
            capabilities=capabilities,
            token_hash=node["token_hash"],
            platform=str(body.get("platform") or node.get("platform") or "windows"),
        )
        return {
            "status": "ok",
            "nodeId": str(updated["id"]),
            "lastHeartbeatAt": updated["last_heartbeat_at"].isoformat()
            if updated.get("last_heartbeat_at")
            else None,
        }

    @app.post("/api/workers/claim")
    async def worker_claim(request: Request) -> dict:
        context = _context(request)
        node = await _current_worker_node(request, context)
        job = await context.jobs.claim_for_worker(node["id"], runtime="windows")
        if job is None:
            return {"job": None}

        payload: dict = {}
        if job.payload_ciphertext:
            try:
                payload = context.payload_crypto.decrypt_json(job.payload_ciphertext)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail="failed to decrypt job payload"
                ) from exc

        slot_id = payload.get("slot_id")
        cursor_agent_id = None
        local_path = payload.get("local_path")
        model_key = await context.users.get_cursor_model_key(
            job.actor_id, default=context.settings.cursor_model
        )
        if slot_id is not None:
            slot = await context.agent_slots.get_slot(job.actor_id, int(slot_id))
            if slot is not None:
                cursor_agent_id = slot.cursor_agent_id
                local_path = local_path or slot.local_path

        mode_raw = str(payload.get("mode") or "ask")
        prompt = str(payload.get("prompt") or "")
        repo_id = payload.get("repo_id")
        memory_block = None
        try:
            mode = UserMode(mode_raw)
        except ValueError:
            mode = UserMode.ASK
        if mode in (UserMode.ASK, UserMode.PLAN) and prompt:
            entries = await context.memory.recall(
                job.actor_id,
                int(repo_id) if repo_id is not None else None,
                prompt,
            )
            memory_block = context.memory.format_recall_block(entries) or None
            logger.info(
                "Windows claim memory recall hits=%s",
                len(entries),
                extra={
                    "user_id": job.actor_id,
                    "job_id": str(job.id),
                    "action": "worker_claim",
                },
            )

        await context.run_events.append(
            job_id=job.id,
            actor_id=job.actor_id,
            event_type="worker.claimed",
            payload={"workerNodeId": str(node["id"]), "modelKey": model_key},
            idempotency_key=f"{job.id}:claimed:{node['id']}",
        )
        return {
            "job": {
                "id": str(job.id),
                "actorId": job.actor_id,
                "kind": job.kind.value,
                "mode": mode_raw,
                "prompt": prompt,
                "repositoryUrl": job.repository_url,
                "repositoryAlias": (job.repository_url or "").rsplit("/", 1)[-1] or "repo",
                "branch": job.branch,
                "localPath": local_path,
                "cursorAgentId": cursor_agent_id,
                "slotId": slot_id,
                "repoId": repo_id,
                "model": model_key,
                "modelKey": model_key,
                "memoryBlock": memory_block,
                "runtime": job.runtime,
            }
        }

    @app.post("/api/workers/runs/{job_id}/events")
    async def worker_run_events(
        job_id: UUID,
        request: Request,
    ) -> dict:
        context = _context(request)
        node = await _current_worker_node(request, context)
        job = await context.jobs.get_internal(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job.worker_node_id is not None and job.worker_node_id != node["id"]:
            raise HTTPException(status_code=403, detail="job assigned to another worker")

        body = await request.json()
        event_type = str(body.get("eventType") or body.get("event_type") or "").strip()
        if not event_type:
            raise HTTPException(status_code=400, detail="eventType required")
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="payload must be an object")
        sequence = int(body.get("sequence") or 0)
        idempotency_key = body.get("idempotencyKey") or body.get("idempotency_key")

        event_id = await context.run_events.append(
            job_id=job.id,
            actor_id=job.actor_id,
            event_type=event_type,
            payload={**payload, "workerNodeId": str(node["id"])},
            sequence=sequence,
            idempotency_key=str(idempotency_key) if idempotency_key else None,
        )

        agent_id = payload.get("agentId") or payload.get("agent_id")
        run_id = payload.get("runId") or payload.get("run_id")
        if agent_id or run_id:
            await context.jobs.set_runtime(
                job.actor_id,
                job.id,
                cursor_agent_id=str(agent_id) if agent_id else None,
                cursor_run_id=str(run_id) if run_id else None,
            )

        if event_type in {"run.finished", "run.failed"}:
            to_status = (
                JobStatus.FAILED
                if event_type == "run.failed" or payload.get("status") == "error"
                else JobStatus.SUCCEEDED
            )
            if to_status == JobStatus.SUCCEEDED:
                try:
                    job_payload = {}
                    if job.payload_ciphertext:
                        job_payload = context.payload_crypto.decrypt_json(
                            job.payload_ciphertext
                        )
                    await context.memory.index_run(
                        tg_user_id=job.actor_id,
                        repo_id=(
                            int(job_payload["repo_id"])
                            if job_payload.get("repo_id") is not None
                            else None
                        ),
                        prompt=str(job_payload.get("prompt") or ""),
                        result=str(
                            payload.get("finalText") or payload.get("final_text") or ""
                        ),
                        mode=str(job_payload.get("mode") or "ask"),
                        run_id=str(
                            payload.get("runId")
                            or payload.get("run_id")
                            or job.cursor_run_id
                            or ""
                        )
                        or None,
                        pr_url=payload.get("prUrl") or payload.get("pr_url"),
                        status="finished",
                        duration_ms=None,
                    )
                except Exception:
                    logger.exception(
                        "Windows run memory index failed",
                        extra={"job_id": str(job.id), "action": "memory_index"},
                    )
            if payload.get("prUrl") or payload.get("totalTokens") is not None:
                await context.jobs.set_result(
                    job.actor_id,
                    job.id,
                    pr_url=payload.get("prUrl"),
                    total_tokens=payload.get("totalTokens"),
                )
            await context.jobs.transition(
                job.actor_id,
                job.id,
                from_statuses=[JobStatus.RUNNING, JobStatus.PLANNING],
                to_status=to_status,
                event_type=event_type,
            )
            await context.notification_outbox.enqueue(
                job_id=job.id,
                actor_id=job.actor_id,
                kind="send",
                telegram_chat_id=job.telegram_chat_id or job.actor_id,
                telegram_message_id=job.telegram_message_id,
                payload={
                    "text": (
                        payload.get("finalText")
                        or payload.get("error")
                        or f"Job {to_status.value}"
                    )[:4000]
                },
                idempotency_key=f"{job.id}:notify:{event_type}",
            )

        return {"accepted": True, "eventId": event_id}

    @app.get("/api/workers")
    async def list_workers(
        request: Request,
        principal: Annotated[TelegramPrincipal, Depends(_current_principal)],
    ) -> list[dict]:
        context = _context(request)
        if context.settings.role_for(principal.user_id) != Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        nodes = await context.worker_nodes.list_all()
        return [_worker_json(node) for node in nodes]

    return app


async def _authorize_worker_register(
    request: Request,
    context: AppContext,
) -> int | None:
    """Owner TMA session or bootstrap token may enroll a worker."""
    authorization = request.headers.get("Authorization")
    bootstrap = (
        context.settings.worker_bootstrap_token.strip()
        or context.settings.beachops_worker_bootstrap_token.strip()
    )
    if bootstrap and authorization:
        raw = authorization.removeprefix("Bearer ").strip()
        if raw and secrets.compare_digest(raw, bootstrap):
            return None
    header_bootstrap = request.headers.get("X-BeachOps-Bootstrap-Token")
    if bootstrap and header_bootstrap and secrets.compare_digest(
        header_bootstrap.strip(), bootstrap
    ):
        return None
    try:
        principal = _validate_authorization(context.settings, authorization)
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail="owner or bootstrap auth required") from exc
    if context.settings.role_for(principal.user_id) != Role.OWNER:
        raise HTTPException(status_code=403, detail="owner role required")
    return principal.user_id


async def _current_worker_node(request: Request, context: AppContext) -> dict:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="worker token required")
    raw = authorization[7:].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="worker token required")
    node = await context.worker_nodes.get_by_token_hash(_hash_worker_token(raw))
    if node is None:
        raise HTTPException(status_code=401, detail="invalid worker token")
    return node


def _hash_worker_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _worker_json(node: dict) -> dict:
    capabilities = node.get("capabilities") or {}
    if isinstance(capabilities, str):
        capabilities = json.loads(capabilities)
    # `is_live` reflects heartbeat freshness (see WorkerNodeRepository); a
    # crashed worker's last-persisted status would otherwise read "online"
    # forever, so the API always reports the derived, time-aware state.
    is_live = node.get("is_live")
    status = node["status"] if is_live is None else ("online" if is_live else "offline")
    return {
        "id": str(node["id"]),
        "hostname": node["hostname"],
        "platform": node["platform"],
        "status": status,
        "capabilities": capabilities,
        "lastHeartbeatAt": node["last_heartbeat_at"].isoformat()
        if node.get("last_heartbeat_at")
        else None,
        "enrolledBy": node.get("enrolled_by"),
        "createdAt": node["created_at"].isoformat() if node.get("created_at") else None,
    }


async def _current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TelegramPrincipal:
    try:
        return await resolve_request_principal(request, authorization)
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail="invalid session") from exc


def _validate_authorization(
    settings: Settings,
    authorization: str | None,
) -> TelegramPrincipal:
    raw = extract_tma_authorization(authorization)
    principal = validate_init_data(
        raw,
        settings.tg_bot_token,
        max_age_sec=settings.web_auth_max_age_sec,
    )
    if settings.role_for(principal.user_id) is None:
        raise TelegramInitDataError("user is not allowlisted")
    return principal


def _context(request: Request) -> AppContext:
    return request.app.state.context


async def _recent_events(
    context: AppContext,
    actor_id: int,
    role: Role | None,
) -> list[dict]:
    where = "" if role == Role.OWNER else "WHERE actor_id = $1"
    args = () if role == Role.OWNER else (actor_id,)
    async with context.pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, job_id, event_type, to_status, created_at
            FROM beachops_job_events
            {where}
            ORDER BY id DESC
            LIMIT 100
            """,
            *args,
        )
    return [
        {
            "id": str(row["id"]),
            "kind": row["event_type"],
            "summary": str(row["to_status"] or row["event_type"]),
            "createdAt": row["created_at"].isoformat(),
            "jobId": str(row["job_id"]),
        }
        for row in rows
    ]


def _job_json(job) -> dict:
    status_map = {
        JobStatus.SUCCEEDED: "completed",
        JobStatus.ACCEPTED: "completed",
        JobStatus.AWAITING_APPROVAL: "blocked",
        JobStatus.REVIEW_REQUIRED: "blocked",
    }
    mapped = status_map.get(job.status, job.status.value)
    agent_id = getattr(job, "cursor_agent_id", None)
    return {
        "id": str(job.id),
        "title": job.summary or job.kind.value,
        "status": mapped,
        "createdAt": (job.created_at or datetime.now(timezone.utc)).isoformat(),
        "repository": job.repository_url.rsplit("/", 1)[-1] if job.repository_url else None,
        "runtime": job.runtime or "cloud",
        "workerNodeId": str(job.worker_node_id) if job.worker_node_id else None,
        "progress": _job_progress(mapped),
        "cursorAgentId": agent_id,
        "cursorUrl": cursor_agent_url(agent_id),
        "branch": getattr(job, "branch", None),
    }


def _repo_json(repo) -> dict:
    return {
        "id": str(repo.id),
        "name": repo.alias,
        "url": repo.github_url,
        "branch": repo.default_branch,
        "status": "ready",
        "active": bool(repo.is_active),
    }


def _agent_slot_json(slot) -> dict:
    return {
        "id": str(slot.id),
        "label": slot.label,
        "runtime": slot.runtime or "cloud",
        "active": bool(slot.is_active),
        "repository": slot.repo_alias,
        "cursorAgentId": slot.cursor_agent_id,
        "cursorUrl": cursor_agent_url(slot.cursor_agent_id),
    }


def _job_progress(status: str) -> int:
    mapping = {
        "queued": 12,
        "planning": 28,
        "approved": 34,
        "running": 62,
        "blocked": 78,
        "awaiting_approval": 78,
        "review_required": 82,
        "revision_requested": 55,
        "completed": 100,
        "accepted": 100,
        "failed": 100,
        "cancelled": 100,
        "rejected": 100,
    }
    return mapping.get(status, 18)


def _queue_stats(jobs) -> dict[str, int]:
    active = 0
    queued = 0
    blocked = 0
    for job in jobs:
        value = job.status.value if hasattr(job.status, "value") else str(job.status)
        if value in {"running", "approved", "planning"}:
            active += 1
        elif value == "queued":
            queued += 1
        elif value in {
            "blocked",
            "awaiting_approval",
            "review_required",
            "paused",
            "revision_requested",
        }:
            blocked += 1
    return {
        "active": active,
        "queued": queued,
        "blocked": blocked,
        "total": len(jobs),
        "running": active,
        "pending": queued,
    }


def _approval_json(approval, *, job=None) -> dict:
    summary = (getattr(job, "summary", None) or "").strip()
    kind_label = {
        ApprovalKind.PLAN_EXECUTION: "План → выполнить",
        ApprovalKind.HIGH_RISK: "Высокий риск",
        ApprovalKind.RESULT_REVIEW: "Ревью результата",
        ApprovalKind.DEPLOY: "Деплой",
        ApprovalKind.MERGE: "Merge",
    }.get(approval.kind, approval.kind.value)
    title = summary[:120] if summary else kind_label
    repo_url = getattr(job, "repository_url", None) or ""
    return {
        "id": str(approval.id),
        "title": title,
        "risk": "high" if approval.kind != ApprovalKind.PLAN_EXECUTION else "medium",
        "requestedAt": (
            approval.requested_at or datetime.now(timezone.utc)
        ).isoformat(),
        "repository": repo_url.rsplit("/", 1)[-1] if repo_url else None,
        "kind": kind_label,
    }


async def _cancel_write_jobs(context: AppContext) -> None:
    jobs = await context.jobs.list_by_status_internal(
        [
            JobStatus.QUEUED,
            JobStatus.APPROVED,
            JobStatus.RUNNING,
            JobStatus.REVISION_REQUESTED,
        ]
    )
    for job in jobs:
        if job.kind != JobKind.CHANGE:
            continue
        if job.cursor_agent_id and job.cursor_run_id:
            await context.cursor.cancel_run(job.cursor_agent_id, job.cursor_run_id)
        await context.jobs.transition(
            job.actor_id,
            job.id,
            from_statuses=[job.status],
            to_status=JobStatus.CANCELLED,
            event_type="panic.cancelled",
        )


async def _speak_job_result(
    context: AppContext,
    websocket: WebSocket,
    job_id: UUID,
) -> None:
    logger.info(
        "Voice speak poll started",
        extra={"job_id": str(job_id), "action": "voice_speak"},
    )
    for _ in range(1800):
        await asyncio.sleep(2)
        job = await context.jobs.get_internal(job_id)
        if job is None:
            logger.warning(
                "Voice speak: job missing",
                extra={
                    "job_id": str(job_id),
                    "action": "voice_speak",
                    "error_code": "job_missing",
                },
            )
            with suppress(Exception):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "job_missing",
                        "message": "Task disappeared",
                    }
                )
            return
        if job.status in {JobStatus.FAILED, JobStatus.BLOCKED, JobStatus.CANCELLED}:
            logger.warning(
                "Voice speak: job %s",
                job.status.value,
                extra={
                    "job_id": str(job_id),
                    "action": "voice_speak",
                    "error_code": job.status.value,
                },
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "code": job.status.value,
                    "message": f"Task {job.status.value}",
                }
            )
            return
        if job.status not in {
            JobStatus.AWAITING_APPROVAL,
            JobStatus.SUCCEEDED,
            JobStatus.REVIEW_REQUIRED,
        }:
            continue
        if not job.cursor_run_id:
            logger.warning(
                "Voice speak: missing cursor_run_id",
                extra={
                    "job_id": str(job_id),
                    "action": "voice_speak",
                    "error_code": "missing_run_id",
                },
            )
            with suppress(Exception):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "missing_run_id",
                        "message": "Task finished without a run id",
                    }
                )
            return
        result = await context.memory.get_by_run_id(job.actor_id, job.cursor_run_id)
        if result is None:
            logger.warning(
                "Voice speak: memory result missing",
                extra={
                    "job_id": str(job_id),
                    "run_id": job.cursor_run_id,
                    "action": "voice_speak",
                    "error_code": "memory_missing",
                },
            )
            with suppress(Exception):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "memory_missing",
                        "message": "Task result is not ready yet",
                    }
                )
            return
        from beachops.domain.voice_persona import to_spoken_briefing

        briefing = to_spoken_briefing(
            result.body,
            max_chars=context.settings.voice_spoken_max_chars,
        )
        await websocket.send_json(
            {"type": "audio.started", "caption": briefing[:500] or result.body[:500]}
        )
        async for chunk in context.speech.stream_pcm(result.body):
            await websocket.send_bytes(chunk)
        await websocket.send_json({"type": "audio.ended"})
        logger.info(
            "Voice speak completed",
            extra={"job_id": str(job_id), "action": "voice_speak"},
        )
        return
