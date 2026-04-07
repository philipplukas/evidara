from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_CONTROL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "platform-control"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./platform_control.db"
    sql_echo: bool = False

    firecrawl_api_key: str | None = None
    firecrawl_base_url: str = "https://api.firecrawl.dev/v2"
    firecrawl_webhook_secret: str | None = None
    firecrawl_webhook_url: str | None = None

    gcp_project_id: str | None = None
    artifact_store_backend: Literal["local", "gcs"] = "local"
    raw_artifact_bucket: str = "evidara-raw-artifacts-dev"
    raw_artifact_prefix: str = "runs"
    raw_artifact_local_dir: Path = Field(default=Path(".data/raw-artifacts"))
    event_publisher_backend: Literal["noop", "pubsub"] = "noop"
    raw_artifact_pubsub_topic: str = "raw-artifact-available"
    artifact_bundle_pubsub_topic: str = "artifact-bundle-available"
    run_dispatch_backend: Literal["inline", "worker"] = "inline"

    # Auth — when any of these are set, matching routes require X-API-Key (see auth.py)
    api_key: str | None = Field(
        default=None,
        description="Legacy full-access key for all protected routes when scoped keys are unset.",
    )
    operator_api_key: str | None = Field(
        default=None,
        description="Admin / control-plane routes (sources, runs, reference data, schedules).",
    )
    service_api_key: str | None = Field(
        default=None,
        description="Pipeline ingest (DI events, Firecrawl webhook path).",
    )

    @field_validator("api_key", "operator_api_key", "service_api_key", mode="before")
    @classmethod
    def _empty_secret_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
