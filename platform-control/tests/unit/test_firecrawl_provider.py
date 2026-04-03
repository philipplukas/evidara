from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform_control.config import Settings
from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.firecrawl_provider import FirecrawlProvider


def _build_source() -> Source:
    return Source(
        source_id="src_123",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )


def _build_run(mode: RunMode = RunMode.PREVIEW) -> Run:
    return Run(
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        mode=mode,
        started_at=datetime(2026, 4, 3, 8, 0, tzinfo=UTC),
    )


def test_build_request_payload_for_crawl_mode_includes_identity_metadata() -> None:
    provider = FirecrawlProvider(
        Settings(
            firecrawl_api_key="secret",
            firecrawl_webhook_url="https://platform-control.example/webhooks/firecrawl",
        )
    )
    version = SourceVersion(
        source_version_id="sv_123",
        source_id="src_123",
        version_label="v1",
        acquisition_spec={
            "seed_url": "https://example.com/decisions",
            "mode": "crawl",
            "include_paths": ["/decisions"],
            "exclude_paths": ["/privacy"],
            "limit": 7,
            "max_discovery_depth": 4,
            "scrape_formats": ["markdown", "html"],
        },
    )

    payload, endpoint = provider._build_request_payload(_build_source(), version, _build_run())

    assert endpoint == "crawl"
    assert payload["metadata"]["run_id"] == "run_123"
    assert payload["metadata"]["source_version_id"] == "sv_123"
    assert payload["includePaths"] == ["/decisions"]
    assert payload["excludePaths"] == ["/privacy"]
    assert payload["webhook"]["events"] == [
        "crawl.started",
        "crawl.page",
        "crawl.completed",
        "crawl.failed",
    ]


def test_build_request_payload_requires_seed_url_for_crawl_mode() -> None:
    provider = FirecrawlProvider(Settings(firecrawl_api_key="secret"))
    version = SourceVersion(
        source_version_id="sv_123",
        source_id="src_123",
        version_label="v1",
        acquisition_spec={"mode": "crawl"},
    )

    with pytest.raises(ProviderConfigurationError):
        provider._build_request_payload(_build_source(), version, _build_run())


def test_build_request_payload_includes_scope_and_replay_metadata() -> None:
    provider = FirecrawlProvider(
        Settings(
            firecrawl_api_key="test-key",
            firecrawl_webhook_url="https://platform-control.example.com/webhooks/firecrawl",
        )
    )
    source = Source(
        source_id="src_123",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    source_version = SourceVersion(
        source_version_id="sv_123",
        source_id="src_123",
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        acquisition_spec={
            "seed_url": "https://example.com/decisions",
            "mode": "crawl",
            "limit": 5,
            "max_discovery_depth": 3,
        },
    )
    run = Run(
        run_id="run_123",
        source_id="src_123",
        source_version_id="sv_123",
        mode=RunMode.PRODUCTION,
        status=RunStatus.RUNNING,
        run_metadata={
            "scope": {
                "kind": "discovered_subset",
                "include_urls": ["https://example.com/decisions/2026/42"],
                "max_resources": 25,
            },
            "replay": {
                "mode": "partial_rerun",
                "parent_run_id": "run_parent_123",
                "reason": "Repair one subset after parser changes",
            },
        },
    )

    payload, endpoint = provider._build_request_payload(source, source_version, run)

    assert endpoint == "crawl"
    assert payload["metadata"]["run_scope"]["kind"] == "discovered_subset"
    assert payload["metadata"]["run_scope"]["max_resources"] == 25
    assert payload["metadata"]["replay"]["mode"] == "partial_rerun"
    assert payload["metadata"]["replay"]["parent_run_id"] == "run_parent_123"
    assert payload["webhook"]["metadata"]["run_scope_kind"] == "discovered_subset"
    assert payload["webhook"]["metadata"]["replay_mode"] == "partial_rerun"
