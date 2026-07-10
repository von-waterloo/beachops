"""Public, redacted API schemas for the BeachOps Mini App."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeResponse(ApiModel):
    user_id: int
    role: str
    writes_enabled: bool


class JobSummary(ApiModel):
    id: int
    owner_user_id: int
    kind: str
    status: str
    repo_alias: str | None = None
    base_branch: str | None = None
    pr_url: str | None = None
    total_tokens: int | None = None
    created_at: datetime
    updated_at: datetime


class JobEventView(ApiModel):
    sequence: int
    event_type: str
    summary: str | None = None
    created_at: datetime


class ApprovalView(ApiModel):
    id: int
    job_id: int
    kind: str
    status: str
    risk_level: str
    expires_at: datetime


class DecisionRequest(ApiModel):
    decision: str = Field(pattern="^(approve|reject|revision)$")
    revision: str | None = Field(default=None, max_length=4000)


class VoiceSpeakRequest(ApiModel):
    text: str = Field(min_length=1, max_length=4000)


class PanicRequest(ApiModel):
    enabled: bool


class WorkerRegisterRequest(ApiModel):
    id: str
    hostname: str = Field(min_length=1, max_length=200)
    platform: str = Field(default="windows", max_length=40)
    capabilities: dict = Field(default_factory=dict)


class WorkerHeartbeatRequest(ApiModel):
    id: str
    hostname: str = Field(min_length=1, max_length=200)
    capabilities: dict = Field(default_factory=dict)


class WorkerClaimRequest(ApiModel):
    workerId: str


class WorkerRunEventRequest(ApiModel):
    type: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)


class DeployDispatchRequest(ApiModel):
    sha: str = Field(min_length=7, max_length=64)
    ref: str | None = Field(default=None, max_length=200)
