# Connector Worker Operations Runbook

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging, prod

## Overview

The connector worker (`platform-control-connector-worker`) is a dedicated
runtime process that polls for pending runs and dispatches them to connector
providers (currently Firecrawl). It runs separately from the platform-control
API to decouple request handling from long-running connector operations.

## Architecture

```text
┌─────────────────────┐      ┌───────────────────────────┐
│  platform-control   │      │  connector-worker         │
│  API                │      │  (Cloud Run Service)      │
│                     │      │                           │
│  POST /runs         │      │  poll loop (5s interval)  │
│    → creates Run    │      │    → SELECT pending runs  │
│      status=PENDING │      │    → dispatch to provider │
│                     │      │    → status=RUNNING       │
└─────────────────────┘      └───────────────────────────┘
         │                              │
         └──────── Postgres ────────────┘
```

**Flow**:

1. API receives `POST /runs`, creates a `Run` row with `status=PENDING`, returns
   immediately (when `run_dispatch_backend=worker`)
2. Worker polls Postgres every N seconds for pending runs
3. Worker dispatches each run to Firecrawl, updates status to `RUNNING`
4. Firecrawl calls back via webhook when the job completes

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND` | `inline` | Set to `worker` on both API and worker |
| `--limit` | `10` | Max runs to dispatch per poll cycle |
| `--interval-seconds` | `5.0` | Seconds between poll cycles |
| `--once` | — | Run a single poll and exit (for testing/cron) |

## Deployment

The worker runs as a **separate Cloud Run Service** (`platform-control-worker`)
using `Dockerfile.worker`. It shares the same codebase and database as the API
but uses a different entrypoint.

### Cloud Run Service Config

- **Image**: `platform-control-worker:latest`
- **Min instances**: 1 (keep warm for polling)
- **Max instances**: 1 (single writer to avoid duplicate dispatch)
- **CPU**: 1 vCPU
- **Memory**: 512 Mi
- **Timeout**: 300s

### Required Secrets

Same as platform-control API:

- `platform_control_dsn` — Postgres connection string
- `firecrawl_api_key` — Firecrawl API key

## Observability

### Structured Logs

The worker emits structured JSON logs compatible with Cloud Logging:

```json
{
  "severity": "INFO",
  "message": "Poll cycle 42: dispatched 3 run(s) in 128.50ms",
  "service": "platform-control-worker",
  "event": "worker_poll_cycle",
  "cycle": 42,
  "dispatched": 3,
  "elapsed_ms": 128.50
}
```

### Key Log Queries

**Worker activity**:

```
resource.type="cloud_run_revision"
jsonPayload.service="platform-control-worker"
jsonPayload.event="worker_poll_cycle"
```

**Worker errors**:

```
resource.type="cloud_run_revision"
jsonPayload.service="platform-control-worker"
severity>=ERROR
```

**Dispatch performance (p95)**:

```
resource.type="cloud_run_revision"
jsonPayload.service="platform-control-worker"
jsonPayload.event="worker_poll_cycle"
jsonPayload.elapsed_ms>500
```

## Operations

### Restart the Worker

```bash
gcloud run services update platform-control-worker-ENV \
  --project PROJECT_ID \
  --region REGION \
  --no-traffic  # drain, then:
gcloud run services update platform-control-worker-ENV \
  --project PROJECT_ID \
  --region REGION \
  --to-latest
```

### Check for Stuck Pending Runs

```sql
SELECT run_id, source_id, status, created_at
FROM runs
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '10 minutes'
ORDER BY created_at ASC;
```

If pending runs are aging, check:

1. Is the worker process running? (Cloud Run console)
2. Are there errors in worker logs?
3. Is the Firecrawl API key valid?
4. Is Postgres reachable from the worker?

### Force-Dispatch a Single Run

For debugging, run a single poll cycle:

```bash
# Local
uv run platform-control-connector-worker --once --limit 1

# In Cloud Run (via gcloud)
gcloud run jobs execute platform-control-worker-one-shot-ENV \
  --project PROJECT_ID \
  --region REGION
```

### Graceful Shutdown

The worker handles `SIGTERM` and `SIGINT`. On signal:

1. Current poll cycle completes
2. No new cycles start
3. Process exits with code 0

Cloud Run sends `SIGTERM` during scaling down or deployments.

## Scaling Considerations

| Scenario | Recommendation |
|----------|---------------|
| Low volume (< 100 runs/day) | Single instance, 5s poll interval |
| Medium volume (100-1000/day) | Single instance, 2s poll interval |
| High volume (1000+/day) | Consider Pub/Sub push trigger instead of polling |

> **Important**: Keep `max_instance_count=1` to prevent duplicate dispatches.
> The current design relies on a single writer. If you need multi-writer,
> implement row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED`).

## Related Resources

- [connector_worker.py](../../platform-control/src/platform_control/connector_worker.py)
- [run_service.py](../../platform-control/src/platform_control/services/run_service.py)
- [Dockerfile.worker](../../platform-control/Dockerfile.worker)
- [Cloud Run tfvars](../../infra/env/dev/runtime.gcp.tfvars.example)
