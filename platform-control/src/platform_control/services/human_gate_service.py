"""Human gate service: loads gate configuration and builds Slack approval messages.

This service is used by Temporal activities to post approval requests to Slack
and by the Slack interaction endpoint to dispatch signals back to the workflow.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml

from platform_control.config import get_settings


class GateConfig:
    """Parsed human-gate YAML entry."""

    def __init__(
        self,
        name: str,
        channel: str,
        timeout: timedelta,
        auto_approve: str = "never",
        fallback: str = "reject",
    ) -> None:
        self.name = name
        self.channel = channel
        self.timeout = timeout
        self.auto_approve = auto_approve
        self.fallback = fallback


class HumanGateService:
    """Coordinates Slack approval workflows for Temporal human gates."""

    def __init__(self, gate_config_path: Path | None = None) -> None:
        self._gates: dict[str, GateConfig] = {}
        if gate_config_path and gate_config_path.exists():
            self._load_config(gate_config_path)

    def _load_config(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, spec in (raw.get("gates") or {}).items():
            timeout_str = spec.get("timeout", "4h").strip().lower()
            if timeout_str.endswith("h"):
                timeout = timedelta(hours=float(timeout_str[:-1]))
            elif timeout_str.endswith("m"):
                timeout = timedelta(minutes=float(timeout_str[:-1]))
            else:
                timeout = timedelta(hours=4)

            self._gates[name] = GateConfig(
                name=name,
                channel=spec["channel"],
                timeout=timeout,
                auto_approve=spec.get("auto_approve", "never"),
                fallback=spec.get("fallback", "reject"),
            )

    def get_gate(self, name: str) -> GateConfig | None:
        return self._gates.get(name)

    async def post_approval_request(
        self,
        *,
        gate_name: str,
        workflow_id: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        """Post an interactive approval message to Slack.

        Returns the Slack message timestamp on success, None on failure.
        """
        settings = get_settings()
        gate = self._gates.get(gate_name)
        if gate is None:
            return None

        slack_token = getattr(settings, "slack_bot_token", None)
        if not slack_token:
            return None

        action_value = json.dumps({"workflow_id": workflow_id, "gate": gate_name})

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Approval: {gate_name}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary},
            },
        ]
        if details:
            detail_text = "\n".join(f"*{k}:* {v}" for k, v in details.items())
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": detail_text}})

        total_seconds = int(gate.timeout.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        timeout_display = f"{hours}h {minutes}m" if minutes else f"{hours}h"

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Timeout: {timeout_display} | Fallback: {gate.fallback}",
                    }
                ],
            }
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "gate_approve",
                        "value": action_value,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "gate_reject",
                        "value": action_value,
                    },
                ],
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {slack_token}"},
                json={
                    "channel": gate.channel,
                    "text": f"Approval required: {gate_name} — {summary}",
                    "blocks": blocks,
                },
            )
            data = resp.json()
            return data.get("ts") if data.get("ok") else None
