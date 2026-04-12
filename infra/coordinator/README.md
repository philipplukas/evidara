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

The NixOS configuration at `infra/nix/hetzner-runner/configuration.nix` includes a systemd service that runs this Compose stack from `/etc/evidara-coordinator/`.

```bash
# Copy files to server
scp -r compose.yml human-gates.yaml .env Dockerfile src/ pyproject.toml root@88.99.26.120:/etc/evidara-coordinator/

# Rebuild NixOS config
ssh root@88.99.26.120 nixos-rebuild switch --flake /path/to/repo#hetzner-runner
```

## Tests

```bash
uv sync --extra dev
uv run pytest tests/ -v
```
