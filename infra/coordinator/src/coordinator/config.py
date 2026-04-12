from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COORDINATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    temporal_target: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "evidara-coordinator"

    openhands_base_url: str = "http://localhost:3000"

    slack_bot_token: str = Field(default="", description="Slack Bot OAuth token (xoxb-...)")
    slack_signing_secret: str = Field(default="", description="Slack app signing secret")

    linear_webhook_secret: str = Field(default="", description="Linear webhook signing secret")
    linear_api_key: str = Field(default="", description="Linear API key for status updates")

    github_token: str = Field(default="", description="GitHub PAT for PR operations")
    github_repo: str = "philipplukas/evidara"

    gate_config_path: Path = Field(
        default=Path("/etc/evidara-coordinator/human-gates.yaml"),
        description="Path to the human gate YAML config",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
