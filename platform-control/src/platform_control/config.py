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
    firecrawl_webhook_record_dir: Path | None = Field(
        default=None,
        description=(
            "Optional directory where each processed Firecrawl webhook payload is "
            "mirrored to disk (one JSON file per payload). When set, enables offline "
            "replay of a real crawl via 'pc ingest --from-fixture'."
        ),
    )

    gcp_project_id: str | None = None
    artifact_store_backend: Literal["local", "gcs", "s3"] = "local"
    raw_artifact_bucket: str = "evidara-raw-artifacts-dev"
    raw_artifact_prefix: str = "runs"
    # S3/MinIO backend — self-hosted object storage (ADR-0029). endpoint_url set for
    # MinIO; left unset for real AWS S3. Credentials fall back to the boto3 default
    # chain (env / instance profile) when not provided here.
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    raw_artifact_local_dir: Path = Field(default=Path(".data/raw-artifacts"))
    cassette_dir: Path = Field(
        default=Path(".data/cassettes"),
        description=(
            "Directory holding cassettes used by CassetteProvider "
            "(shadow-mode + fixture-driven runs)."
        ),
    )
    event_publisher_backend: Literal["noop", "pubsub", "local_outbox", "nats"] = "noop"
    raw_artifact_pubsub_topic: str = "raw-artifact-available"
    artifact_bundle_pubsub_topic: str = "artifact-bundle-available"
    # NATS JetStream backend — self-hosted replacement for Pub/Sub (ADR-0029).
    nats_servers: str = "nats://localhost:4222"
    nats_raw_artifact_subject: str = "evidara.raw-artifact-available"
    nats_artifact_bundle_subject: str = "evidara.artifact-bundle-available"
    run_dispatch_backend: Literal["inline", "worker"] = "inline"
    wizard_orchestrator_backend: Literal["in_memory", "temporal"] = "in_memory"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "platform-control-wizard"
    temporal_target: str = "localhost:7233"
    temporal_tls_ca_path: Path | None = None
    temporal_tls_cert_path: Path | None = None
    temporal_tls_key_path: Path | None = None
    temporal_tls_server_name: str | None = None
    rescore_runner_backend: Literal["document_intelligence", "in_memory"] = Field(
        default="document_intelligence",
        description=(
            "Targeted-rescore runner used by the Temporal worker. Use 'in_memory' only "
            "for explicit local/test fallback; production uses document_intelligence."
        ),
    )

    legifrance_client_id: str | None = None
    legifrance_client_secret: str | None = None

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

    @field_validator(
        "api_key",
        "operator_api_key",
        "service_api_key",
        "legifrance_client_id",
        "legifrance_client_secret",
        mode="before",
    )
    @classmethod
    def _empty_secret_to_none(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @field_validator(
        "temporal_tls_ca_path",
        "temporal_tls_cert_path",
        "temporal_tls_key_path",
        mode="before",
    )
    @classmethod
    def _empty_path_to_none(cls, value: object) -> object | None:
        if value is None or value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
