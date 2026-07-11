"""Shared application context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
from arq.connections import ArqRedis, RedisSettings, create_pool as create_arq_pool
from redis.asyncio import Redis

from beachops.config.settings import Settings
from beachops.db.connection import check_postgres, create_pool
from beachops.db.repositories.agent_slots import AgentSlotRepository
from beachops.db.repositories.approvals import ApprovalRepository
from beachops.db.repositories.audit import AuditRepository
from beachops.db.repositories.callback_tokens import CallbackTokenRepository
from beachops.db.repositories.jobs import JobRepository
from beachops.db.repositories.memory import MemoryRepository
from beachops.db.repositories.orchestration import (
    NotificationOutboxRepository,
    RunEventRepository,
    WorkerNodeRepository,
)
from beachops.db.repositories.github_tokens import GithubTokenRepository
from beachops.db.repositories.passkeys import PasskeyRepository
from beachops.db.repositories.repos import RepoRepository
from beachops.db.repositories.system_state import SystemStateRepository
from beachops.db.repositories.users import UserRepository
from beachops.domain.active_run import ActiveRunInfo
from beachops.services.agent_slots import AgentSlotService
from beachops.services.cancel_store import CancelStore
from beachops.services.cursor_agent import CursorAgentService
from beachops.services.embedding_service import EmbeddingService
from beachops.services.job_queue import JobQueue
from beachops.services.memory_service import MemoryService
from beachops.services.payload_crypto import PayloadCrypto
from beachops.services.rate_limit import RedisRateLimiter
from beachops.services.idempotency import IdempotencyStore
from beachops.services.deploy_history import DeployHistory
from beachops.services.hot_cache import HotCache
from beachops.services.policy_bootstrap import build_repository_policy
from beachops.services.repository_policy import RepositoryPolicyService
from beachops.services.risk_policy import RiskPolicy
from beachops.services.speech_service import SpeechService
from beachops.services.redaction import redact_text
from beachops.services.transcription import TranscriptionService


@dataclass
class AppContext:
    settings: Settings
    pool: asyncpg.Pool
    users: UserRepository
    repos: RepoRepository
    jobs: JobRepository
    run_events: RunEventRepository
    notification_outbox: NotificationOutboxRepository
    worker_nodes: WorkerNodeRepository
    approvals: ApprovalRepository
    callback_tokens: CallbackTokenRepository
    passkeys: PasskeyRepository
    github_tokens: GithubTokenRepository
    audit: AuditRepository
    system_state: SystemStateRepository
    redis: Redis
    arq: ArqRedis
    hot_cache: HotCache
    payload_crypto: PayloadCrypto
    repository_policy: RepositoryPolicyService
    risk_policy: RiskPolicy
    rate_limiter: RedisRateLimiter
    idempotency: IdempotencyStore
    deploy_history: DeployHistory
    agent_slots: AgentSlotService
    memory: MemoryService
    cursor: CursorAgentService
    transcription: TranscriptionService
    speech: SpeechService
    job_queue: JobQueue
    cancel_store: CancelStore
    workspace: Path
    active_runs: dict[int, ActiveRunInfo] = field(default_factory=dict)
    last_prompts: dict[int, tuple[str, float]] = field(default_factory=dict)
    last_user_messages: dict[int, int] = field(default_factory=dict)

    def remember_user_message(self, user_id: int, message_id: int) -> None:
        self.last_user_messages[user_id] = message_id

    @classmethod
    async def create(cls, settings: Settings) -> AppContext:
        pool = await create_pool(settings.database_url)
        await check_postgres(pool)
        redis = Redis.from_url(settings.redis_url, decode_responses=False)
        await redis.ping()
        arq = await create_arq_pool(RedisSettings.from_dsn(settings.redis_url))
        hot_cache = HotCache(redis)
        payload_crypto = PayloadCrypto.from_encoded_key(settings.data_encryption_key)

        workspace = settings.workspace_path
        workspace.mkdir(parents=True, exist_ok=True)

        memory_repo = MemoryRepository(pool)
        embeddings = EmbeddingService(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            redis=redis,
        )
        memory = MemoryService(memory_repo, embeddings, settings)

        repos = RepoRepository(pool)
        slot_repo = AgentSlotRepository(pool)
        agent_slots = AgentSlotService(slot_repo, repos, settings)

        return cls(
            settings=settings,
            pool=pool,
            users=UserRepository(pool),
            repos=repos,
            jobs=JobRepository(pool),
            run_events=RunEventRepository(pool),
            notification_outbox=NotificationOutboxRepository(pool),
            worker_nodes=WorkerNodeRepository(pool),
            approvals=ApprovalRepository(pool),
            callback_tokens=CallbackTokenRepository(pool),
            passkeys=PasskeyRepository(pool),
            github_tokens=GithubTokenRepository(pool),
            audit=AuditRepository(pool),
            system_state=SystemStateRepository(pool, cache=hot_cache),
            redis=redis,
            arq=arq,
            hot_cache=hot_cache,
            payload_crypto=payload_crypto,
            repository_policy=build_repository_policy(settings),
            risk_policy=RiskPolicy(),
            rate_limiter=RedisRateLimiter(redis),
            idempotency=IdempotencyStore(redis),
            deploy_history=DeployHistory(redis),
            agent_slots=agent_slots,
            memory=memory,
            cursor=CursorAgentService(
                api_key=settings.cursor_api_key,
                model=settings.cursor_model,
                workspace=workspace,
            ),
            transcription=TranscriptionService(
                api_key=settings.openai_api_key,
                model=settings.transcribe_model,
                prompt=settings.voice_input_transcribe_prompt or None,
            ),
            speech=SpeechService(
                api_key=settings.openai_api_key,
                model=settings.voice_tts_model,
                voice=settings.voice_tts_voice,
                instructions=settings.voice_tts_instructions or None,
                redact=redact_text,
                max_chars=settings.voice_spoken_max_chars,
            ),
            job_queue=JobQueue(max_queue_depth=settings.job_queue_depth),
            cancel_store=CancelStore(redis),
            workspace=workspace,
        )

    async def close(self) -> None:
        await self.job_queue.drain(timeout=self.settings.shutdown_drain_sec)
        await self.arq.aclose()
        await self.redis.aclose()
        await self.pool.close()
