from __future__ import annotations

import asyncio
import logging
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from platform_control.config import get_settings
from platform_control.temporal.workflows import (
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
    client = await Client.connect(
        settings.temporal_target,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
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
