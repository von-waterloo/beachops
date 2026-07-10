"""Security and control-plane domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    OWNER = "owner"


class JobKind(str, Enum):
    READ = "read"
    ASK = "read"
    PLAN = "plan"
    CHANGE = "change"
    DO = "change"
    RAW_SHELL = "raw_shell"
    SHELL = "raw_shell"
    DEPLOY = "deploy"
    MERGE = "merge"
    PROD_DB = "prod_db"
    SECRETS = "secrets"
    IAM = "iam"
    DELETE = "delete"


class JobStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    PENDING = "queued"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    REVISION_REQUESTED = "revision_requested"
    PAUSED = "paused"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ApprovalKind(str, Enum):
    PLAN_EXECUTION = "plan_execution"
    RESULT_REVIEW = "result_review"
    HIGH_RISK = "high_risk"
    DEPLOY = "deploy"
    MERGE = "merge"
    PROD_DB = "prod_db"
    SECRETS = "secrets"
    IAM = "iam"
    DESTRUCTIVE = "destructive"


class Decision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ApprovalDecision = Decision


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Job:
    id: UUID
    actor_id: int
    kind: JobKind
    status: JobStatus
    risk_level: RiskLevel
    repository_url: str | None = None
    branch: str | None = None
    summary: str = ""
    payload_ciphertext: str | None = None
    cursor_agent_id: str | None = None
    cursor_run_id: str | None = None
    pr_url: str | None = None
    total_tokens: int | None = None
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    idempotency_key: str | None = None
    runtime: str = "cloud"
    worker_node_id: UUID | None = None
    attempt: int = 0
    telegram_updated: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Approval:
    id: UUID
    job_id: UUID
    actor_id: int
    kind: ApprovalKind
    decision: Decision = Decision.PENDING
    requested_at: datetime | None = None
    expires_at: datetime | None = None
    decided_by: int | None = None
    decided_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    id: int | None
    actor_id: int | None
    event_type: str
    action: str
    outcome: str
    job_id: UUID | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class RepositoryPolicy:
    repository_url: str
    allowed_branches: tuple[str, ...]
    protected_branches: tuple[str, ...] = ("main", "master")

