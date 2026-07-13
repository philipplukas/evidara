# Platform-Control Wizard, Temporal, and Argilla — post-merge rollout

> **Status note (ADR-0031, 2026-07-13).** Not a live procedure. **Argilla has been deleted** — skip
> every Argilla step and env var below. **Temporal is deployed in no environment** and
> `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND` stays `in_memory`, so there is no worker to roll
> out. Kept as the record of what a Temporal rollout would involve; #560, #561, and #564 are the
> entry criteria for ever running one. The retention sweep, which used to depend on this rollout,
> now runs as a CronJob — see `docs/runbooks/retention-sweep.md`.

Use this checklist after merging wizard API / Temporal / Argilla work into an environment (staging or production).

## 1. Database migrations

From `platform-control/` with correct `DATABASE_URL` (or your Cloud SQL proxy):

```bash
cd platform-control
uv run alembic upgrade head
```

Confirm new revisions apply in order (wizard foundation tables, then review-task / Argilla-related revisions as shipped in the branch).

## 2. Configuration

Set at minimum:

| Concern | Typical settings |
|---------|------------------|
| Wizard orchestration | `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND=temporal` when workflows should run (default `in_memory` is API-only / local) |
| Temporal | `PLATFORM_CONTROL_TEMPORAL_*` (target, namespace, TLS as required by your cluster) |
| Argilla enqueue | `PLATFORM_CONTROL_ARGILLA_API_BASE_URL`, API key, dataset id when outbound review tasks should POST to Argilla; otherwise enqueue is recorded as skipped |

Exact variable names and semantics live in [`platform-control/src/platform_control/config.py`](../../platform-control/src/platform_control/config.py) and [Platform Control component doc](../components/platform-control.md).

## 3. Temporal worker

Run a worker process that registers the same workflows and task queue as the API. Package entry point:

```bash
# After install from platform-control package / image
platform-control-temporal-worker
```

Use the same Temporal connection settings as the API. Without a worker, `temporal` backend workflows will not progress.

## 4. Smoke checks

- **API health** — existing smoke targets for platform-control.
- **Wizard contracts** — `pytest platform-control/tests/integration/test_wizard_api_contracts.py` (or full `bash scripts/check-platform-control.sh` in CI parity).
- **Reviews** — exercise `POST /v1/reviews/tasks` then `POST /v1/reviews/tasks/{task_id}/decision` per the [extraction review routing runbook](../runbooks/extraction-review-routing.md). (The Argilla enqueue/sync steps that used to be here are gone — ADR-0031.)

## 5. Operator handoff

- Multi-country operator flow: [Platform-Control multi-country operator playbook](../runbooks/platform-control-multi-country-operator-playbook.md)
- Calibration worksheet: [Multi-country wizard calibration worksheet](../runbooks/multi-country-wizard-calibration-worksheet.md)
- Architecture narrative: [Temporal + Argilla wizard](../architecture/temporal-argilla-wizard-architecture.md)
