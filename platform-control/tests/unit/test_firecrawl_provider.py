from __future__ import annotations

from platform_control.config import Settings
from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.firecrawl_provider import FirecrawlProvider


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
