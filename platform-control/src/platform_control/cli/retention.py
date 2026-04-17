"""``pc retention sweep`` — enforce CompliancePolicy.retention_days.

Iterates policies with a configured retention window and purges matching
RawArtifact rows (+ their CapturedResource children + the underlying blob).
``--dry-run`` reports what *would* be deleted without touching anything.
"""

from __future__ import annotations

import argparse


async def run_from_args(namespace: argparse.Namespace) -> int:
    from platform_control.config import get_settings
    from platform_control.database import get_session_maker
    from platform_control.integrations import get_artifact_store
    from platform_control.services.retention_service import RetentionService

    settings = get_settings()
    session_maker = get_session_maker()
    artifact_store = get_artifact_store(settings)

    async with session_maker() as session:
        service = RetentionService(session=session, artifact_store=artifact_store)
        report = await service.sweep(dry_run=namespace.dry_run)

    prefix = "[dry-run] " if namespace.dry_run else ""
    print(
        f"{prefix}retention sweep: "
        f"policies_applied={report.policies_applied} "
        f"artifacts_purged={report.artifacts_purged} "
        f"resources_purged={report.resources_purged} "
        f"blobs_deleted={report.blobs_deleted}"
    )
    return 0


__all__ = ["run_from_args"]
