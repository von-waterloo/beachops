"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from tg_cursor_bot.domain.models import UserMode

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
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    whitelist_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="WHITELIST_USER_IDS"
    )
    admin_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_USER_IDS"
    )
    database_url: str = Field(
        default="postgresql://bot:botsecret@localhost:5432/tg_cursor_bot",
        alias="DATABASE_URL",
    )
    workspace_path: Path = Field(default=Path("./data/workspace"), alias="WORKSPACE_PATH")
    cursor_model: str = Field(default="composer-2.5", alias="CURSOR_MODEL")
    transcribe_model: str = Field(default="gpt-4o-mini-transcribe", alias="TRANSCRIBE_MODEL")
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
    media_group_delay_sec: float = Field(default=1.0, alias="MEDIA_GROUP_DELAY_SEC")
    forward_context_timeout_sec: float = Field(default=15.0, alias="FORWARD_CONTEXT_TIMEOUT_SEC")
    forward_context_max_items: int = Field(default=25, alias="FORWARD_CONTEXT_MAX_ITEMS")
    agent_slots_max: int = Field(default=8, alias="AGENT_SLOTS_MAX", ge=5, le=10)

    @field_validator("whitelist_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def parse_id_list(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, int):
            return [value]
        return [int(part.strip()) for part in str(value).split(",") if part.strip()]

    @field_validator("workspace_path", mode="before")
    @classmethod
    def parse_path(cls, value: object) -> Path:
        return Path(str(value))

    def is_whitelisted(self, user_id: int) -> bool:
        return user_id in self.whitelist_user_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def can_use_mode(self, user_id: int, mode: UserMode) -> bool:
        if mode == UserMode.ASK:
            return True
        return self.is_admin(user_id)

    def has_default_repo(self) -> bool:
        return bool(self.default_repo_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
