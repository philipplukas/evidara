"""Temporal worker for the coordinator.

Registers all workflows and activities on the coordinator task queue.
Run alongside the FastAPI app (separate process or as a background task).
"""

from __future__ import annotations

import asyncio

from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from coordinator.activities import (
    AgentActivities,
    GateActivities,
    GitHubActivities,
    LinearActivities,
)
from coordinator.config import get_settings
from coordinator.gates import load_gate_config
from coordinator.slack_service import SlackService
from coordinator.workflows import AgentTaskWorkflow, HumanGateWorkflow


async def run_worker() -> None:
    settings = get_settings()

    client = await TemporalClient.connect(
        settings.temporal_target, namespace=settings.temporal_namespace
    )

    slack = SlackService(
        bot_token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )

    gate_registry = (
        load_gate_config(settings.gate_config_path)
        if settings.gate_config_path.exists()
        else __import__("coordinator.gates", fromlist=["GateRegistry"]).GateRegistry()
    )

    gate_activities = GateActivities(slack=slack, gate_registry=gate_registry)
    agent_activities = AgentActivities(settings=settings)
    github_activities = GitHubActivities(settings=settings)
    linear_activities = LinearActivities(settings=settings)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[AgentTaskWorkflow, HumanGateWorkflow],
        activities=[
            gate_activities.post_slack_approval,
            agent_activities.dispatch_to_openhands,
            agent_activities.fix_ci_failure,
            github_activities.wait_for_ci,
            github_activities.merge_pr,
            linear_activities.update_issue_status,
            linear_activities.post_comment,
        ],
    )

    print(f"Coordinator worker started on queue '{settings.temporal_task_queue}'")
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
