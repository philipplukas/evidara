# Evidara Coordinator

Autonomous workflow coordinator that bridges Linear issues, OpenHands coding agents, GitHub PRs, and Slack human gates via Temporal durable workflows.

## Architecture

```
Linear webhook → Coordinator API → Temporal → OpenHands → GitHub PR → CI → Slack gate → Merge
```

### Components

- **Coordinator API** (FastAPI) — receives Linear webhooks and Slack interactions
- **Coordinator Worker** (Temporal) — runs `AgentTaskWorkflow` and `HumanGateWorkflow`
- **OpenHands** — autonomous coding agent (separate Docker service)
- **Temporal** — durable workflow orchestration (separate Docker service)
- **Slack App** — interactive approve/reject buttons for human gates

## Slack integration: PARKED (2026-09-08)

Slack is **deactivated, not deleted**. The code, the gate definitions and the
tests all remain; what changed is that the integration now only exists when it is
actually configured:

- `app.py` constructs `SlackService` **only** when both `slack_bot_token` and
  `slack_signing_secret` are set. Otherwise `_slack_service` is `None` and the
  coordinator logs `slack_integration_parked reason=no_credentials_configured`.
- `POST /webhooks/slack` returns **503** while parked. It previously read
  `if _slack_service and not verify(...)`, so a `None` service skipped
  verification altogether and the handler acted on an unauthenticated payload.
- `SlackService.verify_signature` refuses an empty signing secret. HMAC-SHA256
  keyed on `""` is publicly computable, so without that refusal any caller could
  mint a signature that verifies.

To re-activate: set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET`. No code change
is needed, and nothing here has to be rebuilt.

Out of scope: Alertmanager's Slack receiver in
`infra/hetzner/values/kube-prometheus-stack.yaml`. That file is frozen and owned
by `research-platform` (`scripts/check_platform_ownership.py`) — it is not
evidara's to change.

## Human Gates

Gates are defined in `human-gates.yaml`. Each gate specifies:

- `channel` — Slack channel for the approval request
- `timeout` — how long to wait before applying the fallback
- `auto_approve` — condition to skip human approval (`never`, `ci_green`, cost thresholds)
- `fallback` — action on timeout: `reject`, `hold`, or `approve`

## Setup

```bash
cp .env.example .env
# Fill in secrets: Slack, Linear, GitHub tokens

# Run locally
uv sync
uv run uvicorn coordinator.app:app --port 8080 &
uv run python -m coordinator.worker &

# Or via Docker Compose
docker compose up -d
```

## Deploy to Hetzner

> **No supported deploy path.** This stack was deployed by a systemd unit in the NixOS host
> config at `infra/nix/hetzner-runner/configuration.nix`. That host was rebuilt into the
> single-node k3s cluster (ADR-0029) and the NixOS tree has been removed from the repo — see
> git history before the `chore/remove-nix` change if you need the old unit. The dedicated
> server now runs k3s; anything scheduled on it goes through `infra/hetzner/`.
>
> Local `docker compose up -d` (above) still works for development.

## Tests

```bash
uv sync --extra dev
uv run pytest tests/ -v
```
