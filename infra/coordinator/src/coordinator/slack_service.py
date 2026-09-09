"""Slack interactive message service for human gate approvals.

Posts Block Kit messages with approve/reject buttons and handles interaction
payloads from Slack.  Button clicks are forwarded as Temporal signals.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from typing import Any

import httpx

from coordinator.gates import GateDefinition

SLACK_API = "https://slack.com/api"


class SlackService:
    def __init__(self, bot_token: str, signing_secret: str) -> None:
        self._token = bot_token
        self._signing_secret = signing_secret
        self._client = httpx.AsyncClient(
            base_url=SLACK_API,
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=15.0,
        )

    async def post_approval_request(
        self,
        *,
        gate: GateDefinition,
        workflow_id: str,
        run_id: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        """Post a Slack Block Kit message with approve/reject buttons.

        Returns the Slack message `ts` (timestamp ID) on success, None on failure.
        """
        blocks = _build_approval_blocks(
            gate_name=gate.name,
            workflow_id=workflow_id,
            run_id=run_id,
            summary=summary,
            timeout_str=_format_timedelta(gate.timeout),
            details=details,
        )
        resp = await self._client.post(
            "/chat.postMessage",
            json={
                "channel": gate.channel,
                "text": f"Approval required: {gate.name} — {summary}",
                "blocks": blocks,
            },
        )
        data = resp.json()
        if data.get("ok"):
            return data.get("ts")
        return None

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
    ) -> None:
        """Update a previously posted message (e.g. after approval/rejection)."""
        await self._client.post(
            "/chat.update",
            json={"channel": channel, "ts": ts, "text": text, "blocks": []},
        )

    def verify_signature(self, *, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify a Slack request signature."""
        # Defence in depth: `app.py` no longer constructs this without a secret,
        # but if it ever did, an empty key is a PUBLIC key. HMAC-SHA256 keyed on
        # "" is computable by anyone who has the body and timestamp, so every
        # signature would verify. Refuse rather than compute.
        if not self._signing_secret:
            return False

        # Slack sends the timestamp as a header; a non-numeric one used to raise
        # ValueError out of `float()` and surface as a 500 instead of a refusal.
        try:
            age = abs(time.time() - float(timestamp))
        except (TypeError, ValueError):
            return False
        if age > 300:
            return False

        basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            self._signing_secret.encode(),
            basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def close(self) -> None:
        await self._client.aclose()


def _build_approval_blocks(
    *,
    gate_name: str,
    workflow_id: str,
    run_id: str,
    summary: str,
    timeout_str: str,
    details: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit blocks for an approval request."""
    detail_lines = ""
    if details:
        detail_lines = "\n".join(f"  *{k}:* {v}" for k, v in details.items())

    action_value = json.dumps({"workflow_id": workflow_id, "run_id": run_id, "gate": gate_name})

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
    if detail_lines:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": detail_lines}},
        )
    blocks.append(
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Timeout: {timeout_str}"}]},
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
        },
    )
    return blocks


def _format_timedelta(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
