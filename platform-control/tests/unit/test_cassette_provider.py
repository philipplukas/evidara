from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform_control.domain import ExecutionMode, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.cassette_provider import CassetteProvider
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.provider_registry import ProviderRegistry


def _source_version(execution_mode: ExecutionMode = ExecutionMode.SHADOW) -> SourceVersion:
    return SourceVersion(
        source_version_id="sv_shadow",
        source_id="src_shadow",
        version_label="v1",
        status=SourceVersionStatus.APPROVED,
        execution_mode=execution_mode,
        acquisition_spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/"],
        },
    )


def _source() -> Source:
    return Source(
        source_id="src_shadow",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )


def _write_cassette(tmp_path: Path, source_version_id: str, payload: dict) -> Path:
    target = tmp_path / f"{source_version_id}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


@pytest.mark.asyncio
async def test_start_run_replays_recorded_resources(tmp_path: Path) -> None:
    _write_cassette(
        tmp_path,
        "sv_shadow",
        {
            "provider_name": "firecrawl",
            "inline_resources": [
                {
                    "source_url": "https://example.com/decisions/1",
                    "final_url": "https://example.com/decisions/1",
                    "content_type": "text/html",
                    "body": "<html><body>Decision 1</body></html>",
                    "title": "Decision 1",
                    "http_status": 200,
                    "discovery_depth": 1,
                    "metadata": {"replay": True},
                }
            ],
        },
    )

    provider = CassetteProvider(cassette_dir=tmp_path)
    run = Run(
        run_id="run_shadow",
        source_id="src_shadow",
        source_version_id="sv_shadow",
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
    )

    result = await provider.start_run(_source(), _source_version(), run)

    assert result.provider == "firecrawl"
    assert len(result.inline_resources) == 1
    assert result.inline_resources[0].title == "Decision 1"
    assert result.inline_resources[0].metadata["replay"] is True
    assert result.inline_failure_reason is None


@pytest.mark.asyncio
async def test_start_run_raises_when_cassette_missing(tmp_path: Path) -> None:
    provider = CassetteProvider(cassette_dir=tmp_path)
    run = Run(
        run_id="run_shadow",
        source_id="src_shadow",
        source_version_id="sv_shadow",
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
    )

    with pytest.raises(ProviderConfigurationError):
        await provider.start_run(_source(), _source_version(), run)


def test_plan_reports_cassette_missing_without_raising(tmp_path: Path) -> None:
    provider = CassetteProvider(cassette_dir=tmp_path)

    plan = provider.plan(_source(), _source_version())

    assert plan.provider == "cassette"
    assert any("cassette_missing=true" in note for note in plan.notes)


def test_plan_reports_resource_count_when_cassette_present(tmp_path: Path) -> None:
    _write_cassette(
        tmp_path,
        "sv_shadow",
        {
            "inline_resources": [
                {"source_url": "https://example.com/a", "content_type": "text/html", "body": "a"},
                {"source_url": "https://example.com/b", "content_type": "text/html", "body": "b"},
            ],
        },
    )

    plan = CassetteProvider(cassette_dir=tmp_path).plan(_source(), _source_version())

    assert plan.estimated_request_count == 2


def test_registry_resolve_for_version_routes_shadow_to_cassette(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    registry.register(DeterministicHttpProvider())
    registry.register(CassetteProvider(cassette_dir=tmp_path))

    shadow_provider = registry.resolve_for_version(_source_version(ExecutionMode.SHADOW))
    live_provider = registry.resolve_for_version(_source_version(ExecutionMode.LIVE))

    assert shadow_provider.provider_name == "cassette"
    assert live_provider.provider_name == "deterministic_http"
