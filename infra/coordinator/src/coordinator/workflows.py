"""Temporal workflows for autonomous task orchestration.

AgentTaskWorkflow: the main issue-to-PR-to-merge pipeline.
HumanGateWorkflow: reusable approval gate with Slack notification.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from coordinator.activities import (
        AgentActivities,
        GateActivities,
        GitHubActivities,
        LinearActivities,
    )


@workflow.defn
class HumanGateWorkflow:
    """Post a Slack approval request, wait for signal or timeout.

    Returns "approved", "rejected", or the gate's fallback action.
    """

    def __init__(self) -> None:
        self._decision: str | None = None
        self._decided_by: str | None = None

    @workflow.run
    async def run(self, gate_request: dict) -> dict:
        gate_name = gate_request["gate_name"]
        timeout_seconds = gate_request.get("timeout_seconds", 14400)

        await workflow.execute_activity_method(
            GateActivities.post_slack_approval,
            args=[gate_request],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        try:
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=timedelta(seconds=timeout_seconds),
            )
        except TimeoutError:
            self._decision = gate_request.get("fallback", "reject")
            self._decided_by = "timeout"

        return {
            "gate": gate_name,
            "decision": self._decision,
            "decided_by": self._decided_by or "signal",
        }

    @workflow.signal
    def approve(self, user: str = "unknown") -> None:
        self._decision = "approved"
        self._decided_by = user

    @workflow.signal
    def reject(self, user: str = "unknown") -> None:
        self._decision = "rejected"
        self._decided_by = user


@workflow.defn
class AgentTaskWorkflow:
    """End-to-end: Linear issue → OpenHands coding → PR → CI → human gate → merge.

    Steps:
    1. Dispatch coding task to OpenHands
    2. Wait for PR creation
    3. Wait for CI to complete
    4. If CI fails, retry up to max_retries
    5. Request human approval via HumanGateWorkflow
    6. Merge PR and update Linear
    """

    @workflow.run
    async def run(self, task: dict) -> dict:
        issue_id = task["issue_id"]
        issue_title = task.get("title", "")
        issue_body = task.get("body", "")
        max_retries = task.get("max_ci_retries", 3)

        retry_policy = RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0)

        await workflow.execute_activity_method(
            LinearActivities.update_issue_status,
            args=[issue_id, "In Progress"],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        pr_result: dict = await workflow.execute_activity_method(
            AgentActivities.dispatch_to_openhands,
            args=[{
                "issue_id": issue_id,
                "title": issue_title,
                "body": issue_body,
            }],
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        if pr_result.get("status") == "failed":
            await workflow.execute_activity_method(
                LinearActivities.post_comment,
                args=[issue_id, f"Agent failed to create PR: {pr_result.get('error', 'unknown')}"],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            return {"status": "agent_failed", "issue_id": issue_id}

        pr_number = pr_result["pr_number"]
        pr_url = pr_result["pr_url"]

        for attempt in range(max_retries + 1):
            ci_result: dict = await workflow.execute_activity_method(
                GitHubActivities.wait_for_ci,
                args=[pr_number],
                start_to_close_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            if ci_result.get("conclusion") == "success":
                break

            if attempt < max_retries:
                fix_result: dict = await workflow.execute_activity_method(
                    AgentActivities.fix_ci_failure,
                    args=[{
                        "pr_number": pr_number,
                        "ci_logs": ci_result.get("logs", ""),
                        "attempt": attempt + 1,
                    }],
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if fix_result.get("status") == "gave_up":
                    break
        else:
            await workflow.execute_activity_method(
                LinearActivities.post_comment,
                args=[issue_id, f"CI failed after {max_retries} retries. PR: {pr_url}"],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            return {"status": "ci_failed", "issue_id": issue_id, "pr_url": pr_url}

        gate_result = await workflow.execute_child_workflow(
            HumanGateWorkflow.run,
            args=[{
                "gate_name": "merge_to_main",
                "timeout_seconds": 14400,
                "fallback": "reject",
                "summary": f"PR #{pr_number}: {issue_title}",
                "details": {"issue": issue_id, "pr_url": pr_url},
            }],
            id=f"gate_merge_{issue_id}_{pr_number}",
        )

        if gate_result["decision"] != "approved":
            await workflow.execute_activity_method(
                LinearActivities.post_comment,
                args=[issue_id, f"Merge rejected ({gate_result['decided_by']}). PR: {pr_url}"],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            return {"status": "rejected", "issue_id": issue_id, "pr_url": pr_url}

        merge_result: dict = await workflow.execute_activity_method(
            GitHubActivities.merge_pr,
            args=[pr_number],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        await workflow.execute_activity_method(
            LinearActivities.update_issue_status,
            args=[issue_id, "Done"],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        return {
            "status": "merged",
            "issue_id": issue_id,
            "pr_url": pr_url,
            "merge_sha": merge_result.get("sha"),
        }
