from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from platform_control.domain import ReviewTaskStatus, WizardRunState
from platform_control.models.review_task import ReviewTask
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.services.provider_registry import ProviderRegistry


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
# ScopeShardActivities — per-shard discovery / extraction activities
# ---------------------------------------------------------------------------


@dataclass
class ScopeShardActivities:
    """Activities executed inside ``ScopeShardWorkflow`` child workflows.

    Each shard represents a crawl scope (e.g. one country-jurisdiction-authority combination)
    and owns its own retry/circuit-breaker behaviour.

    ``session_factory`` must point to the same database as the rest of platform-control.
    ``provider_registry_factory`` is the seam used by TAR-108 to dispatch the per-shard
    provider run; tests inject a factory returning a registry of fake providers to exercise
    the shard workflow offline.
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

        Reads the wizard run's project scope to determine the crawl configuration,
        updates ``WizardRun.progress`` with per-shard stats, and returns a summary dict.

        The actual provider dispatch (Firecrawl / DeterministicHTTP / RIS-OGD) is wired here;
        today the implementation records progress and returns a stub summary.
        Provider invocation will be added in the shard-dispatch follow-on (TAR-108).

        Returns an empty result dict when the wizard run is not found (e.g. in test scenarios
        where a child workflow is started standalone without a corresponding DB record).
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

            # TODO(TAR-108): dispatch actual provider crawl here using scope config.
            # e.g.:  await _dispatch_provider_run(session, wizard_run, scope, scope_shard_key)
            _ = scope  # consumed once provider dispatch is wired

        return {
            "wizard_run_id": wizard_run_id,
            "scope_shard_key": scope_shard_key,
            "status": "crawl_dispatched",
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
# ReviewDrainActivities — Argilla enqueue + completion-gate activities
# ---------------------------------------------------------------------------


@dataclass
class ReviewDrainActivities:
    """Activities executed inside ``ReviewDrainWorkflow`` child workflows.

    Handles enqueuing pending review tasks to Argilla and polling for queue drain.

    ``session_factory`` must point to the same database as the rest of platform-control.
    Optional ``argilla_api_base_url``, ``argilla_api_key``, ``argilla_dataset_id`` activate
    live Argilla HTTP calls; when absent the enqueue step records the skip in the ledger.
    """

    session_factory: async_sessionmaker[AsyncSession]
    argilla_api_base_url: str | None = None
    argilla_api_key: str | None = None
    argilla_dataset_id: str | None = None

    @activity.defn
    async def enqueue_pending_reviews(self, wizard_run_id: str) -> dict:
        """Enqueue all PENDING review tasks for this wizard run to Argilla.

        Returns a summary dict with ``enqueued``, ``skipped``, ``failed`` counts.
        Idempotent: tasks already enqueued (``argilla_enqueued_at`` is set) are skipped.
        """
        from platform_control.config import Settings
        from platform_control.services.argilla_enqueue_service import ArgillaEnqueueService

        settings = Settings(
            argilla_api_base_url=self.argilla_api_base_url or "",
            argilla_api_key=self.argilla_api_key or "",
            argilla_dataset_id=self.argilla_dataset_id or "",
        )
        argilla = ArgillaEnqueueService(settings)

        enqueued = 0
        skipped = 0
        failed = 0

        async with self.session_factory() as session:
            tasks = (
                await session.scalars(
                    select(ReviewTask).where(
                        ReviewTask.wizard_run_id == wizard_run_id,
                        ReviewTask.status == ReviewTaskStatus.PENDING,
                        ReviewTask.argilla_enqueued_at.is_(None),
                    )
                )
            ).all()

            for task in tasks:
                payload_for_argilla = dict(task.payload or {})
                meta = dict(payload_for_argilla.get("metadata") or {})
                meta.setdefault("wizard_run_id", task.wizard_run_id)
                meta.setdefault("review_task_id", task.review_task_id)
                if task.record_id:
                    meta.setdefault("recordId", task.record_id)
                payload_for_argilla["metadata"] = meta

                result = await argilla.enqueue_record(
                    external_id=task.argilla_external_id,
                    task_payload=payload_for_argilla,
                    idempotency_key=task.review_task_id,
                )
                if result.outcome == "enqueued":
                    task.argilla_enqueued_at = datetime.now(UTC)
                    task.argilla_enqueue_last_error = None
                    enqueued += 1
                elif result.outcome == "skipped_not_configured":
                    skipped += 1
                else:
                    task.argilla_enqueue_last_error = (result.detail or "unknown")[:2000]
                    failed += 1

            await session.commit()

        return {"enqueued": enqueued, "skipped": skipped, "failed": failed}

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
    """Runs :class:`RetentionService.sweep` from a Temporal schedule.

    Deferred imports inside the activity method avoid pulling FastAPI/asyncpg
    machinery into module load when the worker is booted from a minimal
    context. Temporal activities run in the worker process, so re-importing
    on each invocation is fine.

    ``settings_factory`` returns the current ``Settings`` so the activity
    picks up any config change on the next run without restarting the worker.
    """

    session_factory: async_sessionmaker[AsyncSession]
    settings_factory: Callable[[], _SettingsLike] | None = None

    @activity.defn(name="run_retention_sweep")
    async def run_retention_sweep(self, dry_run: bool = False) -> dict:
        """Execute one retention sweep pass, returning the usual report dict.

        Parameters are kept kwarg-free on the Temporal wire (single positional
        bool) so the schedule payload stays trivial. The returned dict matches
        :class:`RetentionSweepReport` so dashboards can log the counts.
        """
        from dataclasses import asdict as _asdict

        from platform_control.config import get_settings
        from platform_control.integrations import get_artifact_store
        from platform_control.services.retention_service import RetentionService

        settings = self.settings_factory() if self.settings_factory is not None else get_settings()
        artifact_store = get_artifact_store(settings)

        async with self.session_factory() as session:
            service = RetentionService(session=session, artifact_store=artifact_store)
            report = await service.sweep(dry_run=dry_run)
        return _asdict(report)


# Placeholder type alias so `settings_factory` can stay optional without
# pulling the full Settings object into the activity module's import graph.
class _SettingsLike:  # pragma: no cover - typing only
    pass
