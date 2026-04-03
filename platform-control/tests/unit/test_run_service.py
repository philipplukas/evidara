from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from platform_control.domain import RunMode, RunStatus
from platform_control.errors import InvalidStateTransitionError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.provider_job import ProviderJob
from platform_control.schemas.run import CreateRunRequest
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    FirecrawlAcquisitionSpec,
)
from platform_control.services.firecrawl_provider import ProviderStartResult
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService


@dataclass
class StubProvider:
    external_job_id: str = "crawl_job_123"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id=self.external_job_id,
            request_payload={"url": "https://example.com"},
            response_payload={"id": self.external_job_id, "success": True},
        )


async def _seed_source_version(session):
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )
    return source, version, source_service


@pytest.mark.asyncio
async def test_production_runs_require_approved_versions(session) -> None:
    source, version, _ = await _seed_source_version(session)
    run_service = RunService(session, StubProvider())

    with pytest.raises(InvalidStateTransitionError):
        await run_service.create_run(
            CreateRunRequest(
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                mode=RunMode.PRODUCTION,
            )
        )


@pytest.mark.asyncio
async def test_create_run_persists_provider_job(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())

    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
        )
    )

    provider_job = await session.scalar(select(ProviderJob).where(ProviderJob.run_id == run.run_id))

    assert run.status is RunStatus.RUNNING
    assert provider_job is not None
    assert provider_job.external_job_id == "crawl_job_123"


@pytest.mark.asyncio
async def test_create_run_persists_explicit_scope_and_replay_metadata(session) -> None:
    source, version, source_service = await _seed_source_version(session)
    await source_service.approve_source_version(version.source_version_id)
    run_service = RunService(session, StubProvider())

    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PRODUCTION,
            scope={
                "kind": "time_window",
                "since": "2026-01-01T00:00:00Z",
                "until": "2026-01-31T23:59:59Z",
                "max_resources": 250,
            },
            replay={
                "mode": "backfill",
                "reason": "Fill January gap after provider outage",
            },
        )
    )

    assert run.run_metadata["scope"]["kind"] == "time_window"
    assert run.run_metadata["scope"]["max_resources"] == 250
    assert run.run_metadata["replay"]["mode"] == "backfill"
    assert run.run_metadata["replay"]["reason"] == "Fill January gap after provider outage"


def test_partial_rerun_requires_parent_run_id() -> None:
    with pytest.raises(ValueError):
        CreateRunRequest(
            source_id="src_123",
            source_version_id="sv_123",
            replay={"mode": "partial_rerun"},
        )
