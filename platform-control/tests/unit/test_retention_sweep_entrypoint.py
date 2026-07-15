"""Unit coverage for the retention-sweep entry points.

The sweep enforces a legal obligation, so what matters is that *the thing the
CronJob actually invokes* deletes expired artifacts:

- :func:`platform_control.retention_sweep.main` — the ``platform-control-retention-sweep``
  console script, which is the CronJob's command. This is the test that proves
  retention runs.
- :meth:`RetentionActivities.run_retention_sweep` — the Temporal adapter, kept
  (ADR-0031) and asserted to delegate to the same shared implementation rather
  than carry its own copy of the sweep.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control import retention_sweep
from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
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


async def _surviving_artifact_count(session_maker: async_sessionmaker[AsyncSession]) -> int:
    async with session_maker() as session:
        return len((await session.scalars(select(RawArtifact.artifact_id))).all())


def test_console_script_purges_expired_artifacts(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CronJob's command performs the sweep — the point of the ADR-0031 move.

    Nothing is injected: ``main`` resolves settings and the session factory from
    the environment exactly as it does inside the CronJob pod (the ``session_maker``
    fixture points that environment at a temp SQLite DB + local artifact dir).
    """
    asyncio.run(_seed_expired_artifact(session_maker, tmp_path))

    exit_code = retention_sweep.main([])

    assert exit_code == 0
    assert asyncio.run(_surviving_artifact_count(session_maker)) == 0

    out = capsys.readouterr().out
    assert "artifacts_purged=1" in out
    assert "resources_purged=1" in out


def test_console_script_dry_run_reports_without_deleting(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(_seed_expired_artifact(session_maker, tmp_path))

    exit_code = retention_sweep.main(["--dry-run"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("[dry-run] ")
    assert "artifacts_purged=1" in out
    assert "blobs_deleted=0" in out
    # Reported, not purged.
    assert asyncio.run(_surviving_artifact_count(session_maker)) == 1


@pytest.mark.asyncio
async def test_temporal_activity_delegates_to_the_same_sweep(
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """The kept Temporal adapter reuses the shared sweep (it holds no copy of its own)."""
    await _seed_expired_artifact(session_maker, tmp_path)

    activity = RetentionActivities(session_factory=session_maker)

    report = await activity.run_retention_sweep(dry_run=False)

    assert report["artifacts_purged"] == 1
    assert report["resources_purged"] == 1
    assert await _surviving_artifact_count(session_maker) == 0
