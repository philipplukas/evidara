"""Slack interaction endpoint for human gate approve/reject buttons.

When a user clicks an approve or reject button in Slack, this endpoint
receives the interaction payload, parses the gate and workflow identifiers,
and signals the corresponding Temporal workflow to proceed.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

from platform_control.config import get_settings

router = APIRouter(tags=["slack"])


@router.post("/webhooks/slack/interactions")
async def slack_interaction(request: Request) -> dict[str, Any]:
    """Handle Slack interactive message payloads.

    Slack sends interaction payloads as application/x-www-form-urlencoded
    with a `payload` field containing JSON.
    """
    raw_body = await request.body()
    form_data = parse_qs(raw_body.decode("utf-8"))
    payload_str = form_data.get("payload", [""])[0]
    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    payload = json.loads(payload_str)
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    value = json.loads(action.get("value", "{}"))
    user = payload.get("user", {}).get("name", "unknown")

    workflow_id = value.get("workflow_id", "")
    gate_name = value.get("gate", "")

    if not workflow_id:
        raise HTTPException(status_code=400, detail="Missing workflow_id in action value")

    settings = get_settings()

    if settings.wizard_orchestrator_backend == "temporal":
        from temporalio.client import Client as TemporalClient

        client = await TemporalClient.connect(
            settings.temporal_target, namespace=settings.temporal_namespace
        )
        handle = client.get_workflow_handle(workflow_id)

        if action_id == "gate_approve":
            await handle.signal("approve", user)
        elif action_id == "gate_reject":
            await handle.signal("reject", user)

    return {
        "ok": True,
        "gate": gate_name,
        "action": action_id,
        "user": user,
        "workflow_id": workflow_id,
    }
