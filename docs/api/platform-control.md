# Platform Control API

Interactive API reference for the platform-control service, generated from the OpenAPI spec at `contracts/api/platform-control.openapi.yaml`.

<swagger-ui src="https://raw.githubusercontent.com/philipplukas/evidara/main/contracts/api/platform-control.openapi.yaml"/>

## Wizard API surface (v1 foundation)

The Temporal + Argilla wizard flow now exposes these operator-facing endpoints:

- `POST /v1/wizard/projects`
- `GET /v1/wizard/projects/{project_id}`
- `POST /v1/wizard/projects/{project_id}/scope`
- `POST /v1/wizard/projects/{project_id}/discovery-plan`
- `POST /v1/wizard/projects/{project_id}/pilot-run`
- `GET /v1/wizard/runs/{run_id}`
- `POST /v1/wizard/runs/{run_id}/approve`
- `POST /v1/wizard/runs/{run_id}/reject`
- `POST /v1/reviews/tasks` — create review task; Argilla HTTP enqueue when configured (see env vars below)
- `POST /v1/reviews/sync-from-argilla`
- `GET /v1/reviews/tasks/{task_id}`

Argilla outbound (optional): set `PLATFORM_CONTROL_ARGILLA_API_BASE_URL`, `PLATFORM_CONTROL_ARGILLA_API_KEY`, and `PLATFORM_CONTROL_ARGILLA_DATASET_ID`. Override bulk path with `PLATFORM_CONTROL_ARGILLA_RECORDS_PATH` (default `/api/v1/datasets/{dataset_id}/records/bulk`). If unset, tasks are still created and `enqueue_outcome` is `skipped_not_configured`.

`GET /v1/wizard/runs/{run_id}` returns a `WizardRunStatus` envelope with:

- `wizard_run_id`, `wizard_project_id`, `workflow_id`, `state`, `state_entered_at`
- `progress` (`total_nodes`, `processed_nodes`, `routed_to_review`, `accepted_records`)
- `quality` (`confidence_distribution`, `conflict_count`, `review_backlog`)
- `health` (`retry_counters`, `last_errors`, `next_retry_window`)

Reference architecture and runbook:

- `docs/architecture/temporal-argilla-wizard-architecture.md`
- `docs/runbooks/argilla-review-routing-and-sync.md`

### Wizard orchestration environment

When using Temporal (`PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND=temporal`), configure:

- `PLATFORM_CONTROL_TEMPORAL_TARGET` — gRPC address (default `localhost:7233`)
- `PLATFORM_CONTROL_TEMPORAL_NAMESPACE` — Temporal namespace (default `default`)
- `PLATFORM_CONTROL_TEMPORAL_TASK_QUEUE` — worker task queue (default `platform-control-wizard`)

Run the worker: `uv run platform-control-temporal-worker` (from `platform-control/`).
