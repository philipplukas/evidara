"""Temporal activities for human gate approval workflows.

These activities interface with the HumanGateService to post Slack approval
requests and check gate status.  They are registered alongside the existing
wizard activities on the platform-control Temporal task queue.
"""

from __future__ import annotations

from dataclasses import dataclass

from temporalio import activity

from platform_control.services.human_gate_service import HumanGateService


@dataclass
class HumanGateActivities:
    """Activities that manage human gate approval requests via Slack."""

    gate_service: HumanGateService

    @activity.defn
    async def post_approval_request(
        self,
        gate_name: str,
        workflow_id: str,
        summary: str,
        details: dict | None = None,
    ) -> dict:
        """Post an approval request to Slack and return the result."""
        ts = await self.gate_service.post_approval_request(
            gate_name=gate_name,
            workflow_id=workflow_id,
            summary=summary,
            details=details,
        )
        return {"posted": ts is not None, "message_ts": ts, "gate_name": gate_name}

    @activity.defn
    async def check_gate_status(self, gate_name: str) -> dict:
        """Check whether a gate is configured and return its settings."""
        gate = self.gate_service.get_gate(gate_name)
        if gate is None:
            return {"exists": False}
        return {
            "exists": True,
            "gate_name": gate.name,
            "channel": gate.channel,
            "timeout_seconds": int(gate.timeout.total_seconds()),
            "auto_approve": gate.auto_approve,
            "fallback": gate.fallback,
        }
