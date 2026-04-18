"""Unit coverage for the Temporal-driven retention path.

- :class:`RetentionActivities.run_retention_sweep` is exercised directly
  against a real session_factory + a real :class:`RetentionService` so the
  activity's integration with sweep logic is guarded.
- :func:`build_schedule` is validated without booting a Temporal cluster
  (the ephemeral test server isn't reachable in this sandbox — see the
  temporal.download 403 failures elsewhere).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schedule_retention import build_schedule
from platform_control.temporal.activities import RetentionActivities


async def _seed_expired_artifact(
    session_maker: async_sessionmaker[AsyncSession], tmp_path: Path
) -> str:
    async with session_maker() as session:
        policy = CompliancePolicy(name="ch-retention-temp", retention_days=1)
        session.add(policy)
        await session.flush()
        session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch",
                name="Switzerland",
                slug="ch",
                compliance_policy_id=policy.compliance_policy_id,
            )
        )
        session.add(
            Authority(
                authority_id="auth_zh_admin",
                jurisdiction_id="jur_ch",
                name="Zurich Administrative Court",
                slug="zh-admin-court",
            )
        )
        source = Source(
            source_id="src_ret",
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
        session.add(source)
        await session.flush()
        session.add(
            SourceVersion(
                source_version_id="sv_ret",
                source_id="src_ret",
                version_label="v1",
                status=SourceVersionStatus.APPROVED,
                acquisition_spec={
                    "provider": "deterministic_http",
                    "seed_urls": ["https://example.com/"],
                },
            )
        )
        session.add(
            Run(
                run_id="run_ret",
                source_id="src_ret",
                source_version_id="sv_ret",
                mode=RunMode.PREVIEW,
                status=RunStatus.COMPLETED,
            )
        )
        blob = tmp_path / "expired.json"
        blob.write_text("{}")
        artifact = RawArtifact(
            run_id="run_ret",
            source_id="src_ret",
            source_version_id="sv_ret",
            storage_path=f"file://{blob}",
            content_type="text/html",
            artifact_metadata={},
        )
        session.add(artifact)
        await session.flush()
        artifact.created_at = datetime.now(UTC) - timedelta(days=30)
        session.add(
            CapturedResource(
                artifact_id=artifact.artifact_id,
                run_id="run_ret",
                source_id="src_ret",
                source_version_id="sv_ret",
                provider_job_id=None,
                source_url="https://example.com/x",
                final_url="https://example.com/x",
                content_type="text/html",
                checksum="abcd",
            )
        )
        await session.commit()
        return artifact.artifact_id


@pytest.mark.asyncio
async def test_activity_drives_retention_sweep(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    await _seed_expired_artifact(session_maker, tmp_path)

    def _settings_factory():
        class _StubSettings:
            artifact_store_backend = "local"
            raw_artifact_local_dir = tmp_path

        return _StubSettings()

    activity = RetentionActivities(
        session_factory=session_maker,
        settings_factory=_settings_factory,
    )

    # Temporal decorates the bound method; call the underlying fn directly
    # so tests don't need a running worker.
    report = await activity.run_retention_sweep(dry_run=False)

    assert report["artifacts_purged"] == 1
    assert report["resources_purged"] == 1


@pytest.mark.asyncio
async def test_activity_dry_run_reports_without_deleting(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    await _seed_expired_artifact(session_maker, tmp_path)

    def _settings_factory():
        class _StubSettings:
            artifact_store_backend = "local"
            raw_artifact_local_dir = tmp_path

        return _StubSettings()

    activity = RetentionActivities(
        session_factory=session_maker,
        settings_factory=_settings_factory,
    )

    report = await activity.run_retention_sweep(dry_run=True)

    assert report["artifacts_purged"] == 1
    assert report["blobs_deleted"] == 0

    # Nothing actually purged.
    async with session_maker() as session:
        surviving = await session.get(
            RawArtifact,
            (
                await session.scalars(__import__("sqlalchemy").select(RawArtifact.artifact_id))
            ).first(),
        )
        assert surviving is not None


def test_build_schedule_shapes_workflow_invocation() -> None:
    schedule = build_schedule(
        task_queue="platform-control-wizard",
        cron="0 4 * * *",
        dry_run=False,
        paused=False,
    )
    action = schedule.action
    # Action targets the right workflow with the right task_queue.
    assert action.workflow == "RetentionSweepWorkflow"
    assert action.task_queue == "platform-control-wizard"
    assert action.args == [False]
    # Spec has the configured cron.
    assert schedule.spec.cron_expressions == ["0 4 * * *"]
    # Default state is active.
    assert schedule.state.paused is False


def test_build_schedule_honours_paused_flag() -> None:
    schedule = build_schedule(
        task_queue="q",
        cron="*/15 * * * *",
        dry_run=True,
        paused=True,
    )
    assert schedule.action.args == [True]
    assert schedule.state.paused is True
    assert schedule.spec.cron_expressions == ["*/15 * * * *"]
