# Platform Control

FastAPI service for source lifecycle, run orchestration, approvals, and raw artifact control-plane workflows in Evidara.

## Local development

```bash
uv sync --group dev
uv run uvicorn platform_control.main:app --reload --app-dir src
```

Seed reference data:

```bash
uv run platform-control-seed-reference-data --dry-run
uv run platform-control-seed-reference-data
```

Sync hierarchy data (jurisdictions, authorities, scrape targets):

```bash
uv run platform-control-sync-hierarchy --dry-run
uv run platform-control-sync-hierarchy
```

Run hierarchy sync via API:

```bash
curl -X POST "http://localhost:8080/v1/reference-data/hierarchy/sync?dry_run=true"
curl -X POST "http://localhost:8080/v1/reference-data/hierarchy/sync"
```

Dispatch queued runs via connector worker:

```bash
uv run platform-control-connector-worker --once
uv run platform-control-connector-worker --limit 25 --interval-seconds 10
```

Local configuration starts from `.env.example`. Keep real secrets out of Git.

## Checks

```bash
../scripts/check-platform-control.sh
```
