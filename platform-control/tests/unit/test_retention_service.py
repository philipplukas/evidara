from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.artifact_store import LocalArtifactStore
from platform_control.services.retention_service import RetentionService


async def _seed_source_with_policy(
    session, *, retention_days: int
) -> tuple[str, str]:
    policy = CompliancePolicy(
        name="ch-retention",
        retention_days=retention_days,
    )
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
        source_id="src_r",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceVersion(
            source_version_id="sv_r",
            source_id="src_r",
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
            run_id="run_r",
            source_id="src_r",
            source_version_id="sv_r",
            mode=RunMode.PREVIEW,
            status=RunStatus.COMPLETED,
        )
    )
    await session.commit()
    return "src_r", "run_r"


async def _seed_artifact(
    session,
    *,
    run_id: str,
    source_id: str,
    created_at: datetime,
    storage_path: str,
) -> str:
    artifact = RawArtifact(
        run_id=run_id,
        source_id=source_id,
        source_version_id="sv_r",
        storage_path=storage_path,
        content_type="text/html",
        artifact_metadata={},
    )
    session.add(artifact)
    await session.flush()
    artifact.created_at = created_at  # override TimestampMixin default
    session.add(
        CapturedResource(
            artifact_id=artifact.artifact_id,
            run_id=run_id,
            source_id=source_id,
            source_version_id="sv_r",
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
async def test_sweep_purges_artifacts_older_than_retention(
    session, tmp_path: Path
) -> None:
    await _seed_source_with_policy(session, retention_days=7)
    old_blob = tmp_path / "old.json"
    old_blob.write_text("{}")
    new_blob = tmp_path / "new.json"
    new_blob.write_text("{}")

    old_id = await _seed_artifact(
        session,
        run_id="run_r",
        source_id="src_r",
        created_at=datetime.now(UTC) - timedelta(days=30),
        storage_path=f"file://{old_blob}",
    )
    new_id = await _seed_artifact(
        session,
        run_id="run_r",
        source_id="src_r",
        created_at=datetime.now(UTC) - timedelta(days=1),
        storage_path=f"file://{new_blob}",
    )

    service = RetentionService(session=session, artifact_store=LocalArtifactStore(tmp_path))
    report = await service.sweep()

    assert report.artifacts_purged == 1
    assert report.resources_purged == 1
    assert report.blobs_deleted == 1
    surviving_ids = list(await session.scalars(select(RawArtifact.artifact_id)))
    assert old_id not in surviving_ids
    assert new_id in surviving_ids
    assert not old_blob.exists()
    assert new_blob.exists()


@pytest.mark.asyncio
async def test_sweep_leaves_artifacts_untouched_without_policy(
    session, tmp_path: Path
) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    source = Source(
        source_id="src_nopolicy",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceVersion(
            source_version_id="sv_nopolicy",
            source_id="src_nopolicy",
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
            run_id="run_nopolicy",
            source_id="src_nopolicy",
            source_version_id="sv_nopolicy",
            mode=RunMode.PREVIEW,
            status=RunStatus.COMPLETED,
        )
    )
    await session.commit()

    stale_blob = tmp_path / "stale.json"
    stale_blob.write_text("{}")
    await _seed_artifact(
        session,
        run_id="run_nopolicy",
        source_id="src_nopolicy",
        created_at=datetime.now(UTC) - timedelta(days=3650),
        storage_path=f"file://{stale_blob}",
    )

    service = RetentionService(session=session, artifact_store=LocalArtifactStore(tmp_path))
    report = await service.sweep()

    assert report.artifacts_purged == 0
    assert stale_blob.exists()
    surviving = await session.scalar(select(func.count()).select_from(RawArtifact))
    assert surviving == 1


@pytest.mark.asyncio
async def test_dry_run_reports_without_deleting(session, tmp_path: Path) -> None:
    await _seed_source_with_policy(session, retention_days=1)
    blob = tmp_path / "will_survive.json"
    blob.write_text("{}")
    await _seed_artifact(
        session,
        run_id="run_r",
        source_id="src_r",
        created_at=datetime.now(UTC) - timedelta(days=5),
        storage_path=f"file://{blob}",
    )

    service = RetentionService(session=session, artifact_store=LocalArtifactStore(tmp_path))
    report = await service.sweep(dry_run=True)

    assert report.artifacts_purged == 1
    assert report.blobs_deleted == 0
    assert blob.exists()
    surviving = await session.scalar(select(func.count()).select_from(RawArtifact))
    assert surviving == 1
