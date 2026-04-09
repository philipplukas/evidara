# Platform Control

FastAPI service for source lifecycle, run orchestration, approvals, and raw artifact control-plane workflows in Evidara.

## Local development

```bash
bash ../scripts/platform-control-demo.sh bootstrap
bash ../scripts/platform-control-demo.sh api
bash ../scripts/platform-control-demo.sh admin-sync
bash ../scripts/platform-control-demo.sh admin
```

Seed reference data:

```bash
bash ../scripts/platform-control-demo.sh seed-dry-run
bash ../scripts/platform-control-demo.sh seed
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

In deployed environments that run this worker, set `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND=worker` on **both** the API and the worker so run creation stays `PENDING` on the API and provider calls execute in the worker process (Firecrawl webhooks remain on the API).

Local configuration starts from `.env.example`. Keep real secrets out of Git.

The code-managed admin app now lives in `admin/` and covers:

- reference data (`Jurisdictions`, `Authorities`)
- source setup (`Sources` plus embedded `Source Versions` actions)
- preview and production run creation from source-version rows
- dedicated preview-review page
- runs list, direct run creation, cancellation, preview review, and run-detail diagnostics

The current app is backed by the existing reference-data and source/version APIs plus
`GET /v1/runs`,
`GET /v1/runs/{run_id}/preview-summary`,
`GET /v1/runs/{run_id}/captured-resources`, `GET /v1/runs/{run_id}/raw-artifacts`,
`GET /v1/runs/{run_id}/provider-jobs`, `GET /v1/runs/{run_id}/processing-status`, and
`GET /v1/runs/{run_id}/document-lifecycle` APIs.

For a step-by-step demo setup, including the local Compose-backed Postgres flow for the React-admin
app, see `../docs/setup/platform-control-local-demo.md`. Historical Retool artifacts remain under
`retool/` as reference material only.

## Checks

```bash
../scripts/check-platform-control.sh
```
