from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.worker import Worker

from platform_control.config import get_settings
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.temporal.activities import (
    RescoreFromCorrectionActivities,
    RetentionActivities,
    ReviewDrainActivities,
    ScopeShardActivities,
    WizardStateActivities,
)
from platform_control.temporal.runners import InMemoryRescoreRunner
from platform_control.temporal.workflows import (
    RescoreFromCorrectionWorkflow,
    RetentionSweepWorkflow,
    ReviewDrainWorkflow,
    ScopeShardWorkflow,
    WizardRunWorkflow,
)

LOGGER = logging.getLogger("platform_control.temporal_worker")


def _setup_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)


async def _async_main() -> None:
    settings = get_settings()

    engine = create_async_engine(settings.database_url)
    session_factory: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    wizard_state_acts = WizardStateActivities(session_factory=session_factory)
    scope_shard_acts = ScopeShardActivities(
        session_factory=session_factory,
        provider_registry_factory=lambda: build_provider_registry(settings),
    )
    review_drain_acts = ReviewDrainActivities(
        session_factory=session_factory,
        argilla_api_base_url=settings.argilla_api_base_url,
        argilla_api_key=settings.argilla_api_key,
        argilla_dataset_id=settings.argilla_dataset_id,
    )
    retention_acts = RetentionActivities(session_factory=session_factory)
    rescore_acts = RescoreFromCorrectionActivities(
        session_factory=session_factory,
        rescore_runner_factory=InMemoryRescoreRunner,
    )

    client = await Client.connect(
        settings.temporal_target,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            WizardRunWorkflow,
            ScopeShardWorkflow,
            ReviewDrainWorkflow,
            RetentionSweepWorkflow,
            RescoreFromCorrectionWorkflow,
        ],
        activities=[
            wizard_state_acts.persist_pilot_completed,
            wizard_state_acts.fetch_scope_shards,
            scope_shard_acts.run_shard_crawl,
            scope_shard_acts.report_shard_progress,
            review_drain_acts.enqueue_pending_reviews,
            review_drain_acts.check_review_drain_complete,
            retention_acts.run_retention_sweep,
            rescore_acts.run_targeted_rescore,
        ],
    )
    LOGGER.info(
        "Temporal worker listening (namespace=%s, task_queue=%s, target=%s)",
        settings.temporal_namespace,
        settings.temporal_task_queue,
        settings.temporal_target,
    )
    await worker.run()


def main() -> None:
    _setup_logging()
    asyncio.run(_async_main())
