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
