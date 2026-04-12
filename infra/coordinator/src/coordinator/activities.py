"""Temporal activities for the coordinator workflows.

Each activity class groups related side effects.  They receive config at
construction time (injected by the worker) and are registered on the Temporal
task queue.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
from temporalio import activity

from coordinator.config import Settings
from coordinator.gates import GateDefinition, GateRegistry
from coordinator.slack_service import SlackService


@dataclass
class GateActivities:
    """Post and manage Slack approval requests."""

    slack: SlackService
    gate_registry: GateRegistry

    @activity.defn
    async def post_slack_approval(self, gate_request: dict) -> dict:
        gate_name = gate_request["gate_name"]
        gate = self.gate_registry.get(gate_name)
        if gate is None:
            return {"posted": False, "reason": f"unknown gate: {gate_name}"}

        ts = await self.slack.post_approval_request(
            gate=gate,
            workflow_id=gate_request.get("workflow_id", "unknown"),
            run_id=gate_request.get("run_id", "unknown"),
            summary=gate_request.get("summary", "Approval required"),
            details=gate_request.get("details"),
        )
        return {"posted": ts is not None, "message_ts": ts}


@dataclass
class AgentActivities:
    """Dispatch coding tasks to OpenHands."""

    settings: Settings

    @activity.defn
    async def dispatch_to_openhands(self, task: dict) -> dict:
        """Create a coding task in OpenHands and wait for PR creation.

        Uses the OpenHands headless/API mode to submit a task.
        Returns {status, pr_number, pr_url} on success.
        """
        issue_id = task["issue_id"]
        title = task.get("title", "")
        body = task.get("body", "")

        prompt = (
            f"You are working on the Evidara repo (github.com/{self.settings.github_repo}).\n\n"
            f"## Task: {title}\n\n{body}\n\n"
            f"## Instructions\n"
            f"1. Clone the repo, create a branch named `agent/{issue_id.lower()}`\n"
            f"2. Implement the changes described above\n"
            f"3. Run relevant tests to verify your changes\n"
            f"4. Create a PR with a clear description referencing {issue_id}\n"
            f"5. Return the PR number and URL\n"
        )

        async with httpx.AsyncClient(
            base_url=self.settings.openhands_base_url,
            timeout=3600.0,
        ) as client:
            try:
                resp = await client.post(
                    "/api/conversations",
                    json={
                        "message": prompt,
                        "repository": f"https://github.com/{self.settings.github_repo}",
                    },
                )
                if resp.status_code >= 400:
                    return {"status": "failed", "error": f"OpenHands API: {resp.status_code}"}

                conversation = resp.json()
                conversation_id = conversation.get("id", "")

                pr_info = await self._poll_for_pr(client, conversation_id)
                return pr_info
            except httpx.HTTPError as exc:
                return {"status": "failed", "error": str(exc)}

    async def _poll_for_pr(self, client: httpx.AsyncClient, conversation_id: str) -> dict:
        """Poll OpenHands conversation until a PR is created or timeout."""
        for _ in range(360):
            await asyncio.sleep(10)
            try:
                resp = await client.get(f"/api/conversations/{conversation_id}")
                data = resp.json()
                state = data.get("state", "running")
                if state == "completed":
                    pr_number = data.get("result", {}).get("pr_number")
                    pr_url = data.get("result", {}).get("pr_url")
                    if pr_number:
                        return {"status": "success", "pr_number": pr_number, "pr_url": pr_url}
                    return {"status": "failed", "error": "No PR created"}
                if state == "failed":
                    return {"status": "failed", "error": data.get("error", "Agent failed")}
            except httpx.HTTPError:
                continue
        return {"status": "failed", "error": "Timeout waiting for agent"}

    @activity.defn
    async def fix_ci_failure(self, context: dict) -> dict:
        """Ask OpenHands to fix a CI failure on an existing PR."""
        pr_number = context["pr_number"]
        ci_logs = context.get("ci_logs", "")
        attempt = context.get("attempt", 1)

        prompt = (
            f"PR #{pr_number} has failing CI. This is fix attempt {attempt}.\n\n"
            f"## CI Failure Logs\n```\n{ci_logs[:5000]}\n```\n\n"
            f"Fix the failing tests/checks and push to the existing PR branch."
        )

        async with httpx.AsyncClient(
            base_url=self.settings.openhands_base_url,
            timeout=1800.0,
        ) as client:
            try:
                resp = await client.post(
                    "/api/conversations",
                    json={"message": prompt},
                )
                if resp.status_code >= 400:
                    return {"status": "gave_up", "error": f"HTTP {resp.status_code}"}
                return {"status": "fix_pushed"}
            except httpx.HTTPError as exc:
                return {"status": "gave_up", "error": str(exc)}


@dataclass
class GitHubActivities:
    """GitHub PR operations via the REST API."""

    settings: Settings

    @activity.defn
    async def wait_for_ci(self, pr_number: int) -> dict:
        """Poll PR check suites until all complete or timeout (30 min)."""
        repo = self.settings.github_repo
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
        }

        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=30.0,
        ) as client:
            for _ in range(60):
                resp = await client.get(f"/repos/{repo}/pulls/{pr_number}")
                pr = resp.json()
                head_sha = pr.get("head", {}).get("sha", "")

                checks_resp = await client.get(
                    f"/repos/{repo}/commits/{head_sha}/check-runs"
                )
                checks = checks_resp.json()
                runs = checks.get("check_runs", [])

                if runs:
                    all_complete = all(r.get("status") == "completed" for r in runs)
                    if all_complete:
                        conclusions = [r.get("conclusion") for r in runs]
                        all_success = all(c in ("success", "skipped") for c in conclusions)
                        failure_logs = ""
                        if not all_success:
                            failed = [r for r in runs if r.get("conclusion") == "failure"]
                            failure_logs = "\n".join(
                                f"- {r['name']}: {r.get('conclusion')}" for r in failed
                            )
                        return {
                            "conclusion": "success" if all_success else "failure",
                            "logs": failure_logs,
                            "sha": head_sha,
                        }

                await asyncio.sleep(30)

        return {"conclusion": "timeout", "logs": "CI did not complete within 30 minutes"}

    @activity.defn
    async def merge_pr(self, pr_number: int) -> dict:
        """Squash-merge a PR."""
        repo = self.settings.github_repo
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
        }

        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=30.0,
        ) as client:
            resp = await client.put(
                f"/repos/{repo}/pulls/{pr_number}/merge",
                json={"merge_method": "squash"},
            )
            data = resp.json()
            return {"sha": data.get("sha"), "merged": data.get("merged", False)}


@dataclass
class LinearActivities:
    """Linear issue operations."""

    settings: Settings

    @activity.defn
    async def update_issue_status(self, issue_id: str, status_name: str) -> dict:
        """Update a Linear issue's status."""
        if not self.settings.linear_api_key:
            return {"updated": False, "reason": "no API key"}

        query = """
        mutation($issueId: String!, $stateId: String!) {
            issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                success
            }
        }
        """
        status_id = await self._resolve_status_id(status_name)
        if not status_id:
            return {"updated": False, "reason": f"status not found: {status_name}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": self.settings.linear_api_key},
                json={"query": query, "variables": {"issueId": issue_id, "stateId": status_id}},
            )
            return {"updated": resp.status_code == 200}

    @activity.defn
    async def post_comment(self, issue_id: str, body: str) -> dict:
        """Post a comment on a Linear issue."""
        if not self.settings.linear_api_key:
            return {"posted": False, "reason": "no API key"}

        query = """
        mutation($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                success
            }
        }
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": self.settings.linear_api_key},
                json={"query": query, "variables": {"issueId": issue_id, "body": body}},
            )
            return {"posted": resp.status_code == 200}

    async def _resolve_status_id(self, status_name: str) -> str | None:
        """Resolve a status name to a Linear state ID.

        Uses a simple mapping; a production version would query the Linear API.
        """
        _STATUS_MAP: dict[str, str] = {
            "In Progress": "3477df82-8d95-4361-8d6c-a9daa9debb90",
            "Done": "806d3740-79a0-4d20-bc05-04834e01793a",
            "Todo": "5416a44c-74e2-427c-85d0-246ff28f27fd",
        }
        return _STATUS_MAP.get(status_name)
