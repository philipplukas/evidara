"""FastAPI application for the coordinator.

Endpoints:
  POST /webhooks/linear    — Linear webhook: dispatches agent tasks when issues
                              move to "Ready for Agent"
  POST /webhooks/slack     — Slack interaction: handles approve/reject button clicks
  GET  /health             — Health check
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client as TemporalClient

from coordinator.config import Settings, get_settings
from coordinator.gates import GateRegistry, load_gate_config
from coordinator.slack_service import SlackService
from coordinator.workflows import AgentTaskWorkflow, HumanGateWorkflow

_temporal_client: TemporalClient | None = None
_slack_service: SlackService | None = None
_gate_registry: GateRegistry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _temporal_client, _slack_service, _gate_registry
    settings = get_settings()

    _temporal_client = await TemporalClient.connect(
        settings.temporal_target, namespace=settings.temporal_namespace
    )

    _slack_service = SlackService(
        bot_token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )

    if settings.gate_config_path.exists():
        _gate_registry = load_gate_config(settings.gate_config_path)
    else:
        _gate_registry = GateRegistry()

    yield

    if _slack_service:
        await _slack_service.close()


app = FastAPI(title="Evidara Coordinator", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/linear")
async def linear_webhook(request: Request) -> dict[str, Any]:
    """Handle Linear webhook events.

    Triggers an AgentTaskWorkflow when an issue is moved to a status whose name
    contains "ready for agent" (case-insensitive).
    """
    body = await request.json()
    action = body.get("action")
    issue_data = body.get("data", {})
    updated_from = body.get("updatedFrom", {})

    if action != "update":
        return {"ignored": True, "reason": "not an update"}

    new_state = (issue_data.get("state") or {}).get("name", "")
    if "ready for agent" not in new_state.lower():
        return {"ignored": True, "reason": f"state is '{new_state}', not agent-ready"}

    issue_id = issue_data.get("identifier", issue_data.get("id", ""))
    title = issue_data.get("title", "")
    description = issue_data.get("description", "")

    if not _temporal_client:
        raise HTTPException(status_code=503, detail="Temporal client not connected")

    workflow_id = f"agent_task_{issue_id}"
    await _temporal_client.start_workflow(
        AgentTaskWorkflow.run,
        {
            "issue_id": issue_id,
            "title": title,
            "body": description,
        },
        id=workflow_id,
        task_queue=get_settings().temporal_task_queue,
    )

    return {"dispatched": True, "workflow_id": workflow_id, "issue_id": issue_id}


@app.post("/webhooks/slack")
async def slack_interaction(request: Request) -> dict[str, Any]:
    """Handle Slack interactive message payloads (approve/reject buttons).

    Slack sends interaction payloads as application/x-www-form-urlencoded with
    a `payload` field containing JSON.
    """
    settings = get_settings()
    raw_body = await request.body()

    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    if _slack_service and not _slack_service.verify_signature(
        body=raw_body, timestamp=timestamp, signature=signature
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

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
    channel = payload.get("channel", {}).get("id", "")
    message_ts = payload.get("message", {}).get("ts", "")

    workflow_id = value.get("workflow_id", "")
    gate_name = value.get("gate", "")

    if not _temporal_client or not workflow_id:
        raise HTTPException(status_code=400, detail="Missing workflow context")

    handle = _temporal_client.get_workflow_handle(f"gate_merge_{value.get('run_id', '')}_{workflow_id}")

    decision = "unknown"
    if action_id == "gate_approve":
        await handle.signal(HumanGateWorkflow.approve, user)
        decision = "approved"
    elif action_id == "gate_reject":
        await handle.signal(HumanGateWorkflow.reject, user)
        decision = "rejected"

    if _slack_service and channel and message_ts:
        await _slack_service.update_message(
            channel=channel,
            ts=message_ts,
            text=f"Gate `{gate_name}` {decision} by {user}",
        )

    return {"ok": True, "decision": decision, "user": user}
