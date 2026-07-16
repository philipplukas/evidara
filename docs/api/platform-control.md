# Platform Control API

Interactive API reference for the platform-control service, rendered from the OpenAPI spec at `contracts/api/platform-control.openapi.yaml`.

That spec is itself **generated from the FastAPI app** ([ADR-0034](../adr/0034-generated-platform-control-contract.md)) — it is byte-for-byte what a running instance serves at `/openapi.json`. To change it, change the routers or Pydantic schemas under `platform-control/src/platform_control/` and regenerate:

```bash
cd platform-control && uv run python ../scripts/generate_platform_control_contract.py
```

`scripts/check-platform-control.sh` fails the build if the committed file and the app disagree. Do not hand-edit it.

The document declares no `servers`: the base URL is per-deployment (see `infra/env/*` for the Cloud Run URLs, `k8s/gitops/` for the cluster ingress). Point your client at the instance you mean. Auth is the `X-API-Key` header ([ADR-0020](../adr/adr-0020-api-authentication.md)).

<swagger-ui src="https://raw.githubusercontent.com/philipplukas/evidara/main/contracts/api/platform-control.openapi.yaml"/>

## Wizard API surface (v1 foundation)

The wizard flow exposes these operator-facing endpoints:

- `POST /v1/wizard/projects`
- `GET /v1/wizard/projects/{project_id}`
- `POST /v1/wizard/projects/{project_id}/scope`
- `POST /v1/wizard/projects/{project_id}/discovery-plan`
- `POST /v1/wizard/projects/{project_id}/pilot-run`
- `GET /v1/wizard/runs/{run_id}`
- `POST /v1/wizard/runs/{run_id}/approve`
- `POST /v1/wizard/runs/{run_id}/reject`
- `POST /v1/reviews/tasks` — route an extraction into the review queue (persisting the task *is* the enqueue)
- `GET /v1/reviews/tasks/{task_id}`
- `POST /v1/reviews/tasks/{task_id}/decision` — close a task with an operator's verdict

Review queue: there is no external review tool and no Argilla env vars. The queue is the `review_tasks` table, read by `platform-control/admin`; what lands in it is decided by the confidence-band policy in [extraction review routing](../runbooks/extraction-review-routing.md). `POST /v1/reviews/sync-from-argilla` was removed in ADR-0031.

`GET /v1/wizard/runs/{run_id}` returns a `WizardRunStatus` envelope with:

- `wizard_run_id`, `wizard_project_id`, `workflow_id`, `state`, `state_entered_at`
- `progress` (`total_nodes`, `processed_nodes`, `routed_to_review`, `accepted_records`)
- `quality` (`confidence_distribution`, `conflict_count`, `review_backlog`)
- `health` (`retry_counters`, `last_errors`, `next_retry_window`)

Reference architecture and runbook:

- `docs/architecture/temporal-argilla-wizard-architecture.md` (Argilla sections superseded by ADR-0031)
- `docs/runbooks/extraction-review-routing.md`

### Wizard orchestration environment

When using Temporal (`PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND=temporal`), configure:

- `PLATFORM_CONTROL_TEMPORAL_TARGET` — gRPC address (default `localhost:7233`)
- `PLATFORM_CONTROL_TEMPORAL_NAMESPACE` — Temporal namespace (default `default`)
- `PLATFORM_CONTROL_TEMPORAL_TASK_QUEUE` — worker task queue (default `platform-control-wizard`)

Run the worker: `uv run platform-control-temporal-worker` (from `platform-control/`).
