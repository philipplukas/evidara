"""Retention sweep driven by :class:`CompliancePolicy.retention_days`.

Purges :class:`RawArtifact` rows (and their :class:`CapturedResource` children)
whose jurisdiction's policy has elapsed the retention window. Hard delete is
the right default for a legal-data product: retention policies are typically
framed by GDPR or source-specific obligations, and soft delete would leave the
regulated data reachable in backups and queries.

Blob removal is best-effort through :meth:`ArtifactStore.delete_blob` — if the
blob can't be found, the DB row still purges so partial states converge on
repeat sweeps rather than piling up un-recoverable orphans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.models.authority import Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.source import Source
from platform_control.services.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetentionSweepReport:
    artifacts_purged: int = 0
    resources_purged: int = 0
    blobs_deleted: int = 0
    policies_applied: int = 0


class RetentionService:
    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self._now = now or datetime.now(UTC)

    async def sweep(self, *, dry_run: bool = False) -> RetentionSweepReport:
        """Delete artifacts older than each jurisdiction's retention window.

        Iterates policies that declare ``retention_days``; for each, deletes
        matching :class:`RawArtifact` rows joined through source + jurisdiction.
        Artifacts with no jurisdiction policy are untouched — absence is the
        operator's explicit "keep indefinitely" signal.
        """
        report = RetentionSweepReport()

        policies = list(
            await self.session.scalars(
                select(CompliancePolicy).where(CompliancePolicy.retention_days.is_not(None))
            )
        )
        for policy in policies:
            # retention_days is narrowed to int by the filter above; mypy-style
            # readers benefit from the local alias.
            days = int(policy.retention_days or 0)
            if days <= 0:
                continue
            cutoff = self._now - timedelta(days=days)

            artifacts = list(
                await self.session.scalars(
                    select(RawArtifact)
                    .join(Source, Source.source_id == RawArtifact.source_id)
                    .join(Jurisdiction, Jurisdiction.jurisdiction_id == Source.jurisdiction_id)
                    .where(Jurisdiction.compliance_policy_id == policy.compliance_policy_id)
                    .where(RawArtifact.created_at < cutoff)
                )
            )
            if not artifacts:
                continue
            report.policies_applied += 1

            for artifact in artifacts:
                logger.info(
                    "retention_purge",
                    extra={
                        "extra_fields": {
                            "event": "retention_purge",
                            "artifact_id": artifact.artifact_id,
                            "run_id": artifact.run_id,
                            "source_id": artifact.source_id,
                            "compliance_policy_id": policy.compliance_policy_id,
                            "cutoff": cutoff.isoformat(),
                        }
                    },
                )
                if dry_run:
                    continue
                if artifact.storage_path:
                    await self.artifact_store.delete_blob(artifact.storage_path)
                    report.blobs_deleted += 1

            if not dry_run:
                artifact_ids = [artifact.artifact_id for artifact in artifacts]
                resources_result = await self.session.execute(
                    delete(CapturedResource).where(
                        CapturedResource.artifact_id.in_(artifact_ids)
                    )
                )
                report.resources_purged += int(resources_result.rowcount or 0)
                artifacts_result = await self.session.execute(
                    delete(RawArtifact).where(RawArtifact.artifact_id.in_(artifact_ids))
                )
                report.artifacts_purged += int(artifacts_result.rowcount or 0)
                await self.session.commit()
            else:
                report.artifacts_purged += len(artifacts)

        return report
