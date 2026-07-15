from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from platform_control.domain import ReviewTaskStatus, RunMode, RunStatus, WizardRunState
from platform_control.models.review_task import ReviewTask
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.services.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


def _sanitize_shard_key(key: str) -> str:
    """Return a safe Temporal workflow-ID segment from an arbitrary shard key string."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:100] or "default"


# ---------------------------------------------------------------------------
# WizardStateActivities — state-persistence callbacks from workflow → DB
# ---------------------------------------------------------------------------


@dataclass
class WizardStateActivities:
    """Activities that persist wizard run state transitions into the platform-control database.

    These are invoked from Temporal workflows so the authoritative Postgres/SQLite state stays
    in sync with long-running workflow execution without polling.

    Pass the same ``session_factory`` used by the application (or the test fixture's factory)
    so activities operate against the correct database.
    """

    session_factory: async_sessionmaker[AsyncSession]

    @activity.defn
    async def persist_pilot_completed(self, wizard_run_id: str) -> None:
        """Advance WizardRun state from PilotRun → HumanGateApproval.

        Called by WizardRunWorkflow after the pilot phase finishes.
        Idempotent: if the run is already at or past HumanGateApproval the call is a no-op.
        """
        async with self.session_factory() as session:
            wizard_run = await session.get(WizardRun, wizard_run_id)
            if wizard_run is None:
                raise RuntimeError(f"WizardRun not found: {wizard_run_id}")
            if wizard_run.state is not WizardRunState.PILOT_RUN:
                # Idempotent: already transitioned — skip without error.
                return
            now = datetime.now(UTC)
            wizard_run.state = WizardRunState.HUMAN_GATE_APPROVAL
            wizard_run.state_entered_at = now
            ledger = await session.scalar(
                select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == wizard_run_id)
            )
            if ledger is not None:
                transitions = dict(ledger.state_transitions or {})
                events = list(transitions.get("events", []))
                events.append(
                    {
                        "state": WizardRunState.HUMAN_GATE_APPROVAL.value,
                        "entered_at": now.isoformat(),
                        "event": "pilot_completed",
                    }
                )
                transitions["events"] = events
                ledger.state_transitions = transitions
            await session.commit()

    @activity.defn
    async def fetch_scope_shards(self, wizard_run_id: str) -> list[str]:
        """Return the list of scope-shard keys for the given wizard run.

        Reads ``WizardProject.scope`` and returns explicit shard keys when present;
        otherwise derives one shard key per domain, falling back to ``["default"]``.
        """
        async with self.session_factory() as session:
            wizard_run = await session.get(WizardRun, wizard_run_id)
            if wizard_run is None:
                return ["default"]
            project = await session.get(WizardProject, wizard_run.wizard_project_id)
            if project is None:
                return ["default"]
            scope = dict(project.scope or {})
            # Explicit shard list wins.
            if "shards" in scope:
                shard_keys = [_sanitize_shard_key(str(k)) for k in scope["shards"] if k]
                return shard_keys or ["default"]
            # Derive one shard per domain (capped to 20) as a reasonable fallback.
            domains = [str(d) for d in scope.get("domains", []) if d]
            if domains:
                return [_sanitize_shard_key(f"domain_{d.replace('.', '_')}") for d in domains[:20]]
            return ["default"]


# ---------------------------------------------------------------------------
# Provider dispatch helper (TAR-108)
# ---------------------------------------------------------------------------


async def _dispatch_provider_run(
    *,
    session: AsyncSession,
    provider_registry_factory: Callable[[], ProviderRegistry] | None,
    source_id: str,
    source_version_id: str,
    scope_shard_key: str,
    scope: dict[str, Any],
    wizard_run_id: str,
) -> dict[str, Any]:
    """Create a Run, resolve the provider, dispatch, and return summary stats.

    Reuses :class:`RunService` so inline-resource persistence, artifact-bundle
    publishing, rate-limiting, and robots compliance all work identically to the
    regular (non-wizard) run path.
    """
    from platform_control.services.run_service import RunService

    source = await session.get(Source, source_id)
    source_version = await session.get(SourceVersion, source_version_id)
    if source is None or source_version is None:
        return {
            "status": "skipped_source_not_found",
            "nodes_discovered": 0,
            "records_accepted": 0,
            "records_sent_to_review": 0,
            "fatal_error_count": 0,
        }

    if provider_registry_factory is None:
        return {
            "status": "skipped_no_registry",
            "nodes_discovered": 0,
            "records_accepted": 0,
            "records_sent_to_review": 0,
            "fatal_error_count": 0,
        }

    registry = provider_registry_factory()

    run_metadata: dict[str, Any] = {
        "scope": {
            "kind": scope.get("scope_kind", "full_source"),
            "max_resources": scope.get("max_resources"),
        },
        "wizard_run_id": wizard_run_id,
        "scope_shard_key": scope_shard_key,
    }
    run = Run(
        source_id=source.source_id,
        source_version_id=source_version.source_version_id,
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
        run_metadata=run_metadata,
    )
    session.add(run)
    await session.flush()

    run_service = RunService(session, provider_registry=registry)
    try:
        pending_publications = await run_service._dispatch_run(source, source_version, run)
    except Exception:
        logger.exception(
            "Provider dispatch failed for shard %s (wizard_run=%s)",
            scope_shard_key,
            wizard_run_id,
        )
        run.status = RunStatus.FAILED
        run.failure_reason = "Provider dispatch raised an exception."
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return {
            "status": "failed",
            "run_id": run.run_id,
            "nodes_discovered": 0,
            "records_accepted": 0,
            "records_sent_to_review": 0,
            "fatal_error_count": 1,
        }

    await session.commit()
    await session.refresh(run)

    # Publish artifact-bundle events outside the DB transaction.
    try:
        await run_service._publish_pending_dispatch_events([pending_publications])
    except Exception:
        logger.warning(
            "Post-dispatch event publishing failed for run %s (non-fatal)",
            run.run_id,
            exc_info=True,
        )

    return {
        "status": run.status.value,
        "run_id": run.run_id,
        "nodes_discovered": run.captured_resources_count,
        "records_accepted": run.captured_resources_count,
        "records_sent_to_review": 0,
        "fatal_error_count": 1 if run.status is RunStatus.FAILED else 0,
    }


# ---------------------------------------------------------------------------
# ScopeShardActivities — per-shard discovery / extraction activities
# ---------------------------------------------------------------------------


@dataclass
class ScopeShardActivities:
    """Activities executed inside ``ScopeShardWorkflow`` child workflows.

    Each shard represents a crawl scope (e.g. one country-jurisdiction-authority combination)
    and owns its own retry/circuit-breaker behaviour.

    ``session_factory`` must point to the same database as the rest of platform-control.
    ``provider_registry_factory`` returns a ``ProviderRegistry`` used to resolve and
    dispatch the per-shard provider run.  Tests inject a factory returning a registry
    of fake providers to exercise the shard workflow offline.
    """

    session_factory: async_sessionmaker[AsyncSession]
    provider_registry_factory: Callable[[], ProviderRegistry] | None = field(default=None)

    @activity.defn
    async def run_shard_crawl(
        self,
        wizard_run_id: str,
        scope_shard_key: str,
        resume_token: str | None,
    ) -> dict:
        """Execute the crawl/discovery/extraction slice for one scope shard.

        Reads the wizard run's project scope and discovery plan to determine the
        crawl configuration, creates a ``Run`` record, dispatches the resolved
        provider, persists inline resources, and returns a summary dict with real
        acquisition statistics.

        The ``discovery_plan`` must contain ``source_id`` and ``source_version_id``
        referencing an existing Source and approved SourceVersion.  When either is
        missing the shard is skipped with ``status=skipped_no_source_ref``.

        Returns an empty result dict when the wizard run is not found (e.g. in test
        scenarios where a child workflow is started standalone without a
        corresponding DB record).
        """
        async with self.session_factory() as session:
            wizard_run = await session.get(WizardRun, wizard_run_id)
            if wizard_run is None:
                return {
                    "wizard_run_id": wizard_run_id,
                    "scope_shard_key": scope_shard_key,
                    "status": "skipped_run_not_found",
                }

            project = await session.get(WizardProject, wizard_run.wizard_project_id)
            scope = dict(project.scope if project else {})
            discovery_plan = dict(project.discovery_plan if project else {})

            # Mark shard as running.
            progress = dict(wizard_run.progress or {})
            shards_progress: dict = dict(progress.get("shards", {}))
            shard_entry = dict(shards_progress.get(scope_shard_key, {}))
            shard_entry["status"] = "running"
            shard_entry["started_at"] = datetime.now(UTC).isoformat()
            if resume_token:
                shard_entry["resume_token"] = resume_token
            shards_progress[scope_shard_key] = shard_entry
            progress["shards"] = shards_progress
            wizard_run.progress = progress
            await session.commit()

            # Resolve source + version from discovery plan (or scope fallback).
            source_id = discovery_plan.get("source_id") or scope.get("source_id")
            source_version_id = discovery_plan.get("source_version_id") or scope.get(
                "source_version_id"
            )
            if not source_id or not source_version_id:
                return {
                    "wizard_run_id": wizard_run_id,
                    "scope_shard_key": scope_shard_key,
                    "status": "skipped_no_source_ref",
                }

            result = await _dispatch_provider_run(
                session=session,
                provider_registry_factory=self.provider_registry_factory,
                source_id=str(source_id),
                source_version_id=str(source_version_id),
                scope_shard_key=scope_shard_key,
                scope=scope,
                wizard_run_id=wizard_run_id,
            )

        return {
            "wizard_run_id": wizard_run_id,
            "scope_shard_key": scope_shard_key,
            **result,
        }

    @activity.defn
    async def report_shard_progress(
        self,
        wizard_run_id: str,
        scope_shard_key: str,
        stats: dict,
    ) -> None:
        """Persist shard completion stats into ``WizardRun.progress``.

        ``stats`` may contain ``nodes_discovered``, ``records_accepted``,
        ``records_sent_to_review``, and ``fatal_error_count``.
        """
        async with self.session_factory() as session:
            wizard_run = await session.get(WizardRun, wizard_run_id)
            if wizard_run is None:
                return

            progress = dict(wizard_run.progress or {})
            shards_progress = dict(progress.get("shards", {}))
            shard_entry = dict(shards_progress.get(scope_shard_key, {}))
            shard_entry["status"] = "complete"
            shard_entry["completed_at"] = datetime.now(UTC).isoformat()
            shard_entry.update(stats)
            shards_progress[scope_shard_key] = shard_entry
            progress["shards"] = shards_progress

            # Roll up aggregate progress counters.
            total_nodes = int(progress.get("total_nodes", 0)) + int(
                stats.get("nodes_discovered", 0)
            )
            accepted = int(progress.get("accepted_records", 0)) + int(
                stats.get("records_accepted", 0)
            )
            routed = int(progress.get("routed_to_review", 0)) + int(
                stats.get("records_sent_to_review", 0)
            )
            progress["total_nodes"] = total_nodes
            progress["accepted_records"] = accepted
            progress["routed_to_review"] = routed
            wizard_run.progress = progress
            await session.commit()


# ---------------------------------------------------------------------------
# ReviewDrainActivities — review-queue completion gate
# ---------------------------------------------------------------------------


@dataclass
class ReviewDrainActivities:
    """Activities executed inside ``ReviewDrainWorkflow`` child workflows.

    Polls until the run's review queue has drained. There is no enqueue step:
    persisting a ``ReviewTask`` *is* the enqueue — the queue is the table, which the
    admin app reads. The Argilla push that used to live here is gone (ADR-0031, #563).

    ``session_factory`` must point to the same database as the rest of platform-control.
    """

    session_factory: async_sessionmaker[AsyncSession]

    @activity.defn
    async def check_review_drain_complete(self, wizard_run_id: str) -> bool:
        """Return True when all review tasks for the run have reached a terminal status.

        Called periodically by ``ReviewDrainWorkflow`` until the review queue drains.
        A run with zero review tasks is considered immediately complete.
        """
        from sqlalchemy import func

        async with self.session_factory() as session:
            total: int = (
                await session.scalar(  # type: ignore[assignment]
                    select(func.count())
                    .select_from(ReviewTask)
                    .where(ReviewTask.wizard_run_id == wizard_run_id)
                )
                or 0
            )
            if total == 0:
                return True

            pending: int = (
                await session.scalar(  # type: ignore[assignment]
                    select(func.count())
                    .select_from(ReviewTask)
                    .where(
                        ReviewTask.wizard_run_id == wizard_run_id,
                        ReviewTask.status == ReviewTaskStatus.PENDING,
                    )
                )
                or 0
            )
            return pending == 0


# ---------------------------------------------------------------------------
# RetentionActivities — schedule-driven compliance-policy retention sweep
# ---------------------------------------------------------------------------


@dataclass
class RetentionActivities:
    """Thin Temporal adapter over :func:`platform_control.retention_sweep.run_retention_sweep`.

    **This is not how the retention sweep is scheduled.** Hard-delete retention is
    a legal obligation, so it runs from a Kubernetes CronJob against the
    ``platform-control-retention-sweep`` console script — not from a Temporal
    worker, which is deployed in no environment (ADR-0031). This activity is kept
    only so the Temporal code stays correct and callable if a worker is ever stood
    up; it delegates to the same shared implementation and holds no sweep logic of
    its own.

    Deferred import inside the activity method avoids pulling FastAPI/asyncpg
    machinery into module load when the worker is booted from a minimal context.

    ``settings_factory`` returns the current ``Settings`` so the activity picks up
    any config change on the next run without restarting the worker.
    """

    session_factory: async_sessionmaker[AsyncSession]
    settings_factory: Callable[[], _SettingsLike] | None = None

    @activity.defn(name="run_retention_sweep")
    async def run_retention_sweep(self, dry_run: bool = False) -> dict:
        """Execute one retention sweep pass, returning the usual report dict.

        Parameters are kept kwarg-free on the Temporal wire (single positional
        bool) so the payload stays trivial. The returned dict matches
        :class:`RetentionSweepReport` so dashboards can log the counts.
        """
        from dataclasses import asdict as _asdict

        from platform_control.retention_sweep import run_retention_sweep

        settings = self.settings_factory() if self.settings_factory is not None else None
        report = await run_retention_sweep(
            dry_run=dry_run,
            settings=settings,
            session_factory=self.session_factory,
        )
        return _asdict(report)


# Placeholder type alias so `settings_factory` can stay optional without
# pulling the full Settings object into the activity module's import graph.
class _SettingsLike:  # pragma: no cover - typing only
    pass


# ─── Rescore-from-correction (#427) ──────────────────────────────────────────


@dataclass(slots=True)
class RescoreFromCorrectionActivities:
    """Activity that drives the targeted rescore for an applied correction.

    The activity is intentionally thin: it dispatches to the DI runtime
    via a small protocol (`TargetedRescoreRunner`) so unit tests can
    swap a stub in. The protocol's contract: take a target identifier,
    return one of `changed`/`unchanged`/`failed` plus the resulting
    DI run id (when applicable). The activity then persists the
    outcome on the correction's payload via
    `CorrectionService.record_rescore_outcome` so the admin metrics
    widget (#432) can count outcomes without touching the rescore
    pipeline directly.
    """

    session_factory: async_sessionmaker[AsyncSession]
    rescore_runner_factory: Callable[[], TargetedRescoreRunner]

    @activity.defn
    async def run_targeted_rescore(self, payload: Any) -> dict[str, Any]:
        # Workflow imports `RescoreFromCorrectionInput` lazily via the
        # passed-through imports block; activities receive the dataclass
        # serialized via Temporal's data-converter so `payload` here is
        # a dict-like / dataclass with the same shape.
        correction_id = _extract_field(payload, "correction_id")
        target_entity_type = _extract_field(payload, "target_entity_type")
        target_entity_id = _extract_field(payload, "target_entity_id")

        runner = self.rescore_runner_factory()
        try:
            outcome, resulting_run_id = await runner.run_targeted_rescore(
                target_entity_type=target_entity_type,
                target_entity_id=target_entity_id,
                correction_id=correction_id,
            )
        except Exception as exc:
            logger.exception(
                "rescore_runner_failed",
                extra={"correction_id": correction_id},
            )
            outcome = "failed"
            resulting_run_id = None
            failure_reason = str(exc)
        else:
            failure_reason = None

        # Late-import to keep the activity module's startup time and
        # circular-import surface small; the import is only needed
        # when the activity actually runs.
        from platform_control.services.correction_service import CorrectionService

        async with self.session_factory() as session:
            service = CorrectionService(session)
            await service.record_rescore_outcome(
                correction_id,
                outcome=outcome,
                resulting_run_id=resulting_run_id,
            )

        logger.info(
            "rescore_completed",
            extra={
                "correction_id": correction_id,
                "outcome": outcome,
                "resulting_run_id": resulting_run_id,
                "failure_reason": failure_reason,
            },
        )
        return {
            "correction_id": correction_id,
            "outcome": outcome,
            "resulting_run_id": resulting_run_id,
            "failure_reason": failure_reason,
        }


class TargetedRescoreRunner:
    """Protocol for the DI side of a targeted rescore (#427).

    Implementations live in document-intelligence and call into the
    processing runtime to re-extract the targeted document or
    commentary insight. Returns the outcome plus the resulting run id.
    """

    async def run_targeted_rescore(
        self,
        *,
        target_entity_type: str,
        target_entity_id: str,
        correction_id: str,
    ) -> tuple[str, str | None]:  # pragma: no cover - protocol only
        raise NotImplementedError


def _extract_field(payload: Any, name: str) -> str:
    """Pull a string field out of the activity payload regardless of shape."""

    if isinstance(payload, dict):
        value = payload.get(name)
    else:
        value = getattr(payload, name, None)
    if not isinstance(value, str):
        raise ValueError(f"rescore activity payload is missing field {name!r}")
    return value
