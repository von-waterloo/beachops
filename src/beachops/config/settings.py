"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from beachops.domain.cursor_tokens import CursorTokenKey
from beachops.domain.models import UserMode
from beachops.domain.security import Role

# Cursor Cloud Agent (Anthropic vision backend): up to 100 images per request.
# Above 20, max image dimension drops from 8000px to 2000px per provider rules.
CURSOR_MAX_IMAGES_PER_PROMPT = 100
DEFAULT_PHOTO_MAX_COUNT = 20
DEFAULT_DOCUMENT_MAX_CHARS = 30_000
DEFAULT_DOCUMENT_MAX_BYTES = 20 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tg_bot_token: str = Field(alias="TG_BOT_TOKEN")
    cursor_api_key: str = Field(alias="CURSOR_API_KEY")
    cursor_api_key_mt2: str = Field(default="", alias="CURSOR_API_KEY_MT2")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    whitelist_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="WHITELIST_USER_IDS"
    )
    admin_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_USER_IDS"
    )
    viewer_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="VIEWER_USER_IDS"
    )
    operator_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="OPERATOR_USER_IDS"
    )
    owner_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="OWNER_USER_IDS"
    )
    database_url: str = Field(
        default="postgresql://bot:botsecret@localhost:5432/tg_cursor_bot",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    data_encryption_key: str = Field(default="", alias="DATA_ENCRYPTION_KEY")
    repository_policy_json: str = Field(default="{}", alias="REPOSITORY_POLICY_JSON")
    webapp_base_url: str = Field(default="", alias="WEBAPP_BASE_URL")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_repo: str = Field(default="", alias="GITHUB_REPO")
    github_deploy_workflow: str = Field(
        default="deploy-prod.yml", alias="GITHUB_DEPLOY_WORKFLOW"
    )
    github_deploy_dispatch: bool = Field(
        default=False, alias="GITHUB_DEPLOY_DISPATCH"
    )
    github_deploy_ref: str = Field(default="main", alias="GITHUB_DEPLOY_REF")
    self_improve_enabled: bool = Field(default=False, alias="SELF_IMPROVE_ENABLED")
    self_improve_repo_url: str = Field(default="", alias="SELF_IMPROVE_REPO_URL")
    self_improve_branches: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["dev"],
        alias="SELF_IMPROVE_BRANCHES",
    )
    default_runtime: Literal["cloud", "windows"] = Field(
        default="cloud", alias="DEFAULT_RUNTIME"
    )
    worker_bootstrap_token: str = Field(default="", alias="WORKER_BOOTSTRAP_TOKEN")
    # Alias accepted for docs / Windows worker install scripts.
    beachops_worker_bootstrap_token: str = Field(
        default="",
        alias="BEACHOPS_WORKER_BOOTSTRAP_TOKEN",
    )
    web_auth_max_age_sec: int = Field(
        default=3600, alias="WEB_AUTH_MAX_AGE_SEC", ge=60, le=86_400
    )
    web_session_ttl_sec: int = Field(
        default=43_200, alias="WEB_SESSION_TTL_SEC", ge=300, le=2_592_000
    )
    web_auth_challenge_ttl_sec: int = Field(
        default=300, alias="WEB_AUTH_CHALLENGE_TTL_SEC", ge=60, le=900
    )
    voice_realtime_model: str = Field(
        default="gpt-realtime-whisper", alias="VOICE_REALTIME_MODEL"
    )
    # Nested STT inside Realtime transcription session (Dec 2025 snapshot).
    voice_input_transcribe_model: str = Field(
        default="gpt-4o-mini-transcribe-2025-12-15",
        alias="VOICE_INPUT_TRANSCRIBE_MODEL",
    )
    # Pin Dec 2025 TTS snapshot (alias gpt-4o-mini-tts → same; pin for stability).
    voice_tts_model: str = Field(
        default="gpt-4o-mini-tts-2025-12-15", alias="VOICE_TTS_MODEL"
    )
    # marin / cedar = best quality per OpenAI; cedar reads more "commander".
    voice_tts_voice: str = Field(default="cedar", alias="VOICE_TTS_VOICE")
    # Empty = built-in BeachOps orchestrator instructions (domain/voice_persona.py).
    voice_tts_instructions: str = Field(default="", alias="VOICE_TTS_INSTRUCTIONS")
    voice_spoken_max_chars: int = Field(
        default=900, alias="VOICE_SPOKEN_MAX_CHARS", ge=120, le=4000
    )
    voice_max_session_sec: int = Field(
        default=300, alias="VOICE_MAX_SESSION_SEC", ge=30, le=900
    )
    callback_token_ttl_sec: int = Field(
        default=600, alias="CALLBACK_TOKEN_TTL_SEC", ge=30, le=86_400
    )
    callback_rate_limit: int = Field(
        default=30, alias="CALLBACK_RATE_LIMIT", ge=1, le=10_000
    )
    callback_rate_window_sec: int = Field(
        default=60, alias="CALLBACK_RATE_WINDOW_SEC", ge=1, le=3_600
    )
    workspace_path: Path = Field(default=Path("./data/workspace"), alias="WORKSPACE_PATH")
    cursor_model: str = Field(default="composer-2.5", alias="CURSOR_MODEL")
    transcribe_model: str = Field(
        default="gpt-4o-mini-transcribe-2025-12-15", alias="TRANSCRIBE_MODEL"
    )
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    default_branch: str = Field(default="dev", alias="DEFAULT_BRANCH")
    default_repo_url: str = Field(default="", alias="DEFAULT_REPO_URL")
    job_queue_depth: int = Field(default=2, alias="JOB_QUEUE_DEPTH")
    memory_recall_k: int = Field(default=3, alias="MEMORY_RECALL_K")
    memory_list_limit: int = Field(default=10, alias="MEMORY_LIST_LIMIT")
    memory_embed_max_chars: int = Field(default=8000, alias="MEMORY_EMBED_MAX_CHARS")
    stream_thinking: Literal["off", "preview", "admin"] = Field(
        default="preview",
        alias="STREAM_THINKING",
    )
    stream_thinking_preview_chars: int = Field(
        default=300,
        alias="STREAM_THINKING_PREVIEW_CHARS",
    )
    photo_max_count: int = Field(
        default=DEFAULT_PHOTO_MAX_COUNT,
        alias="PHOTO_MAX_COUNT",
        ge=1,
        le=CURSOR_MAX_IMAGES_PER_PROMPT,
    )
    document_max_chars: int = Field(
        default=DEFAULT_DOCUMENT_MAX_CHARS,
        alias="DOCUMENT_MAX_CHARS",
        ge=1000,
        le=100_000,
    )
    document_max_bytes: int = Field(
        default=DEFAULT_DOCUMENT_MAX_BYTES,
        alias="DOCUMENT_MAX_BYTES",
        ge=1024,
        le=20 * 1024 * 1024,
    )
    media_group_delay_sec: float = Field(default=6.0, alias="MEDIA_GROUP_DELAY_SEC")
    shutdown_drain_sec: float = Field(default=15.0, alias="SHUTDOWN_DRAIN_SEC")
    prompt_coalesce_sec: float = Field(
        default=5.0,
        alias="PROMPT_COALESCE_SEC",
        ge=0.0,
        le=30.0,
    )
    forward_context_timeout_sec: float = Field(default=25.0, alias="FORWARD_CONTEXT_TIMEOUT_SEC")
    forward_context_max_items: int = Field(default=25, alias="FORWARD_CONTEXT_MAX_ITEMS")
    agent_slots_max: int = Field(default=8, alias="AGENT_SLOTS_MAX", ge=5, le=10)

    @field_validator(
        "whitelist_user_ids",
        "admin_user_ids",
        "viewer_user_ids",
        "operator_user_ids",
        "owner_user_ids",
        mode="before",
    )
    @classmethod
    def parse_id_list(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, int):
            return [value]
        return [int(part.strip()) for part in str(value).split(",") if part.strip()]

    @field_validator("self_improve_branches", mode="before")
    @classmethod
    def parse_branch_list(cls, value: object) -> list[str]:
        if value is None or value == "":
            return ["dev"]
        if isinstance(value, list):
            branches = [str(item).strip() for item in value if str(item).strip()]
            return branches or ["dev"]
        branches = [part.strip() for part in str(value).split(",") if part.strip()]
        return branches or ["dev"]

    @field_validator("workspace_path", mode="before")
    @classmethod
    def parse_path(cls, value: object) -> Path:
        return Path(str(value))

    def self_improve_repo_normalized(self) -> str | None:
        """Canonical HTTPS URL of the self-improve repo, or None if disabled/unset."""
        if not self.self_improve_enabled:
            return None
        raw = self.self_improve_repo_url.strip()
        if not raw:
            return None
        from beachops.services.repository_policy import (
            RepositoryPolicyError,
            normalize_github_url,
        )

        try:
            return normalize_github_url(raw)
        except RepositoryPolicyError:
            return None

    def is_self_improve_repo(self, repository_url: str) -> bool:
        target = self.self_improve_repo_normalized()
        if target is None:
            return False
        from beachops.services.repository_policy import (
            RepositoryPolicyError,
            normalize_github_url,
        )

        try:
            return normalize_github_url(repository_url) == target
        except RepositoryPolicyError:
            return False

    def role_for(self, user_id: int) -> Role | None:
        """Resolve explicit RBAC with owner > operator > viewer precedence.

        Legacy admins retain owner privileges and legacy whitelist entries retain
        viewer access, so deployments can migrate the environment incrementally.
        """
        if user_id in self.owner_user_ids or user_id in self.admin_user_ids:
            return Role.OWNER
        if user_id in self.operator_user_ids:
            return Role.OPERATOR
        if user_id in self.viewer_user_ids or user_id in self.whitelist_user_ids:
            return Role.VIEWER
        return None

    def is_whitelisted(self, user_id: int) -> bool:
        return self.role_for(user_id) is not None

    def is_admin(self, user_id: int) -> bool:
        """Compatibility capability used by existing write-mode UI."""
        return self.role_for(user_id) in {Role.OPERATOR, Role.OWNER}

    def can_approve(self, user_id: int) -> bool:
        return self.role_for(user_id) == Role.OWNER

    def can_panic(self, user_id: int) -> bool:
        return self.role_for(user_id) == Role.OWNER

    def can_use_mode(self, user_id: int, mode: UserMode) -> bool:
        if mode == UserMode.ASK:
            return self.is_whitelisted(user_id)
        return self.role_for(user_id) in {Role.OPERATOR, Role.OWNER}

    def has_default_repo(self) -> bool:
        return bool(self.default_repo_url.strip())

    def has_cursor_token(self, token_key: str) -> bool:
        if token_key == CursorTokenKey.MT2.value:
            return bool(self.cursor_api_key_mt2.strip())
        return bool(self.cursor_api_key.strip())

    def cursor_api_key_for(self, token_key: str) -> str:
        if token_key == CursorTokenKey.MT2.value and self.cursor_api_key_mt2.strip():
            return self.cursor_api_key_mt2
        return self.cursor_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
