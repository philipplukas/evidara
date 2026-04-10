# E2E step 7 investigation — dev (2026-04-09)

Operator follow-up after empty `processing-status` / `document-lifecycle` for completed smoke runs.

## Commands run (reproducible)

**Project:** Evidara dev runtime is **`project-dacd6b7b-dc96-4534-b82`** (GitHub Actions `GCP_PROJECT_ID_DEV`). It is **not** the default in `scripts/e2e-smoke-test.sh` (`data-platform-dev-492214`); always export `GCP_PROJECT_ID` for local `gcloud` + scripts.

```bash
export GCP_PROJECT_ID=project-dacd6b7b-dc96-4534-b82
gcloud config set project "${GCP_PROJECT_ID}"
```

**Pub/Sub push wiring (dev):** subscriptions point at the expected Cloud Run URLs:

- `artifact-bundle-available` → `di-consumer-dev` `…/internal/events/artifact-bundles:process`
- `document-processing-status-updated` → `platform-control-api-dev` `…/v1/di/events/document-processing-status-updated`
- `document-processed` → `platform-control-api-dev` `…/v1/di/events/document-processed`

**platform-control `/v1/di/events`:** no request logs matched in the smoke window (consistent with **no successful publishes** from DI for these runs).

**Cloud Logging — `di-consumer-dev` request log (sample window 2026-04-09 19:20–19:32Z):**

- Repeated **`POST …/internal/events/artifact-bundles:process` → HTTP 500**
- **`userAgent: APIs-Google`** → Pub/Sub push (not browser)
- **Conclusion:** the bundle ingress **accepts** the push at the edge but the **application handler fails** (`ProcessingError` → 500 in [`document_intelligence/consumer/app.py`](../../../document-intelligence/src/document_intelligence/consumer/app.py)). Until that returns 2xx, **no status/processed messages** reach platform-control → e2e step 7 stays empty.

Example filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="di-consumer-dev"
httpRequest.requestUrl=~"artifact-bundles"
```

**DLQ (`platform-control-document-processing-status-updated-dlq-sub`):** at least one dead-lettered message existed (older run `run_01knep9t38evh6tc57xj8mt5th`, **5 delivery attempts** from subscription `platform-control-document-processing-status-updated`). That indicates **past** PC push delivery problems for status events; it is separate from the **current** smoke symptom if DI never publishes new events.

**Caution:** `gcloud pubsub subscriptions pull` **acknowledges** messages by default. Prefer **Console → subscription → Metrics** or a dedicated replay workflow for inspection; do not pull production DLQs casually.

**Pub/Sub metrics:** use **GCP Console → Monitoring → Metrics explorer** for `pubsub.googleapis.com/topic/send_request_count` and subscription push metrics if you need publish vs delivery counts; this environment did not use a supported `gcloud monitoring time-series` CLI path.

## Run IDs checked

| Run ID | `/v1/runs` | processing-status | document.processed |
|--------|------------|-------------------|----------------------|
| `run_01knstj8tcc3s12zhn0fvh7w5q` | completed, captures OK | empty | empty |
| `run_01knsv782pa1ebf17d9zcjwd4n` | completed, captures OK | empty | empty |

Local check: `./scripts/check-di-signals-for-run.sh` with `GCP_PROJECT_ID` set as above.

## Root cause (confirmed)

Cloud Logging showed:

`document_intelligence.ingest.loaders.BundleLoadError: bundle manifest did not contain a selectable primary artifact`

**Live `di-consumer-dev` Cloud Run** was running an **older `document-intelligence` package** (traceback line numbers did not match current `pipeline.py` / `consumer/app.py` on `main`).

The **same** bundle manifest object in GCS for a failed smoke run (`abm_*.json`) was downloaded and parsed with **current** repo code: it contains **`artifact_role: primary_document`** and **`text/html`**. `_select_primary_artifact` succeeds locally — so the failure is **image / deploy drift**, not bad platform-control manifests for deterministic smoke.

**Action:** rebuild and **redeploy `di-consumer-dev`** from current `main` (or whatever commit you want in production). After deploy, confirm ingress returns **200** and logs show processing (or `artifact_bundle_process_failed` with a real `code=` if something else breaks).

### Other `ProcessingError` paths (after redeploy)

[`process_artifact_bundle_event`](../../../document-intelligence/src/document_intelligence/processing_runtime.py) with `require_surface_uris=True` raises **`missing_runtime_surface_config`** if surface URIs are missing. **stdout** on Cloud Run may still be sparse; use **`artifact_bundle_process_failed`** **ERROR** logs from [`consumer/app.py`](../../../document-intelligence/src/document_intelligence/consumer/app.py) after deploy.

## Next engineering actions

1. **Cloud Run → `di-consumer-dev` → Revisions → Environment variables:** confirm `DI_SURFACES_ROOT_URI` (or the three explicit published URIs) matches the bucket used in CI preflight (`gs://evidara-document-intelligence-surfaces-dev/published` or env-specific).
2. **Redeploy** consumer after fixing config; confirm ingress returns **200** and logs show **`status":"processed"`** payload shape.
3. **Re-run** `./scripts/check-di-signals-for-run.sh RUN_ID` on a fresh smoke run, then **E2E Smoke Dev**.
4. **DLQ:** triage `platform-control-document-processing-status-updated-dlq-sub` per [dlq-triage-and-replay.md](../dlq-triage-and-replay.md) if delivery errors persist **after** DI publishes.
5. **GitHub `main`:** ensure the e2e **Summarize** step uses **`python3`** (self-hosted runner may not provide `python`).

## References

- [m5-evidence-checklist.md](../m5-evidence-checklist.md#strategic-phases) — strategic phases
- [check-di-signals-for-run.sh](../../../scripts/check-di-signals-for-run.sh)
