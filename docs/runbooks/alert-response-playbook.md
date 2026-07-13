# Alert Response Playbook

Owner: Platform team
Last reviewed: 2026-04-11
Last verified: Not yet verified
Applies to: dev, staging, prod

## Overview

This playbook documents how to respond to automated alerts from the Evidara
monitoring stack. Each alert links to a specific section below.

For SLI/SLO definitions, see [docs/adr/sli-slo-definitions.md](../adr/sli-slo-definitions.md).

> **Two monitoring stacks are described in this file.** The [Hetzner pipeline
> alerts](#hetzner-pipeline-alerts-adr-0031) below fire from Prometheus/Alertmanager on
> the self-hosted k3s cluster and are the **live** ones (ADR-0031). The Cloud
> Run / Pub/Sub / Cloud Logging sections further down describe the retired GCP stack and
> are kept for historical reference until they are ported or removed — do not expect a
> `gcloud` command in them to work against the current runtime (ADR-0029).

## Hetzner pipeline alerts (ADR-0031)

Rules: `infra/hetzner/observability/alerts.yaml`. Dashboard: Grafana →
**Evidara → pipeline funnel** (`docs/setup/hetzner-observability.md` for access).

**Open the funnel dashboard first, always.** Every alert below is a statement about one
stage of the pipeline; the funnel shows you all of them at once and tells you *where* the
work stopped, which is the only question that matters. Reading it takes five seconds.

### DocumentsReadAliasUnresolved — **page**

**Meaning**: the OpenSearch alias `documents-read` resolves to no physical index. Search
returns an empty page for **every** query. This is a total outage of the core product
feature, and it ran undetected for weeks (#549) because every pod stayed `Running` and
`1/1 Ready` throughout.

```bash
kubectl -n evidara exec deploy/legal-search-api -- \
  wget -qO- http://opensearch-cluster-master.evidara.svc:9200/_cat/aliases?v
```

1. If **no aliases exist**: the index was never created or was deleted. `legal-search-api`
   bootstraps it idempotently on startup, so restart it —
   `kubectl -n evidara rollout restart deploy/legal-search-api` — and confirm both
   `documents-read` and `documents-write` appear, pointing at the same physical index.
   Check `OPENSEARCH_BOOTSTRAP_ON_STARTUP` is not set to `false`.
2. The index will come back **empty**. Documents must be replayed:
   [projection reindex/backfill](./projection-reindex-backfill.md).
3. If the alias exists but the alert persists, the API cannot reach OpenSearch — check
   `SearchIndexProbeDown` and the OpenSearch pod.

### DocumentsAliasesDiverged — **page**

**Meaning**: `documents-read` and `documents-write` point at *different* physical indices.
Projections land in one, search reads the other. Both operations "succeed" forever and no
new document is ever findable (#551).

Fix the aliases atomically, then verify both resolve to the same index. See
[projection reindex/backfill](./projection-reindex-backfill.md) — a versioned cutover
that half-completed is the usual cause.

### SearchIndexEmpty — **page**

**Meaning**: the alias resolves, but there are zero documents behind it. A wiped index, a
failed reindex, or a projection path that has never delivered anything.

Check the funnel: if `documents indexed` is 0 while `DI messages processed` is not, treat
it as `ProjectionPathLeaking`. If both are 0, the leak is upstream — look at `runs
launched`.

### SearchZeroResultRateHigh — **page**

**Meaning**: over 95% of searches returned nothing across 15 minutes (with at least 5
queries, so a quiet night cannot page).

Look at the `backend errors (served as empty)` line on the funnel dashboard's search
panel first. The API **degrades a failed OpenSearch call into an empty result set**, so
"no matches" and "the cluster is dead" look identical to a user:

- **errors > 0** → OpenSearch is failing. Check the pod, disk, and JVM heap.
- **errors == 0** → the index or the analyzer is wrong. A bad reindex or a mapping change
  is the usual cause; compare against `legal-search/api/src/core/opensearch/`.

### ProjectionPathLeaking — **page**

**Meaning**: `document-intelligence` processed messages in the last hour and legal-search
indexed **zero** documents. The chain NATS → `projection-bridge` →
`POST /v1/projections/events` is dropping everything.

```bash
kubectl -n evidara get pods -l app=projection-bridge      # is it even deployed?
kubectl -n evidara logs deploy/projection-bridge --tail=50
```

`projection-bridge` not being deployed at all was one of the original silent failures.
Then check `di_projection_forwards_total{outcome="dead_lettered"}` and
[DLQ triage](./dlq-triage-and-replay.md).

### EvidaraTargetDown — **page**

**Meaning**: Prometheus cannot scrape a target. **Every alert that depends on that
target's metrics is now blind** — this alert exists to stop the monitoring from failing
silently in the same way the pipeline did.

```bash
kubectl -n evidara get pods
kubectl -n evidara get servicemonitor,podmonitor
```

A pod that is `Running` but not scrapeable usually means its `/metrics` endpoint broke or
a port name changed (`ServiceMonitor`/`PodMonitor` target ports **by name**).

### Warning tier

| Alert | Meaning | First step |
|---|---|---|
| `SearchBackendErrors` | OpenSearch calls are failing; users see empty pages, not errors | OpenSearch pod health, heap, disk |
| `SearchIndexProbeDown` | legal-search cannot reach OpenSearch to probe the index — the alias alerts are blind | OpenSearch pod + `OPENSEARCH_NODE` |
| `DiConsumerDeadLettering` | di-consumer is dead-lettering artifact bundles | [DLQ triage](./dlq-triage-and-replay.md) |
| `ProjectionBridgeDeadLettering` | projection-bridge is dead-lettering `document.processed` | [DLQ triage](./dlq-triage-and-replay.md) |
| `JetStreamConsumerBacklogGrowing` | a consumer is stuck, crash-looping, or slower than the producer | `kubectl -n evidara logs` the consumer; check its restart count |
| `JetStreamRedeliveriesClimbing` | messages are being nak'd and retried — the handler is failing | Consumer logs; look for a repeating `error_type` |

---

## Operational drill evidence (TAR-67)

For table-top or live alert drills, capture: alert name, environment, acknowledgement time, first Cloud Logging query used, and resolution path (rollback, config fix, or “no action / benign”). Link DLQ-related drills to [DLQ triage and replay](dlq-triage-and-replay.md#operational-drill-evidence-tar-67) and traffic-affecting drills to [release and rollback](release-rollback.md#operational-drill-evidence-tar-67). Store attachments on **TAR-67** / **TAR-69** unless the evidence pack is already cleared for [`docs/runbooks/evidence/`](evidence/README.md).

## Alert Triage Flow

```text
Alert fires
  │
  ├─ Acknowledge in Slack / email
  │
  ├─ Identify: which service, which environment?
  │
  ├─ Is this a known issue or recent deploy?
  │   ├─ Yes → rollback or apply known fix
  │   └─ No  → investigate below
  │
  └─ Follow the relevant section
```

---

## Tier 1 — Critical Alerts

### DLQ Messages Accumulating

**Alert**: `DLQ messages accumulating: {subscription} ({environment})`

**Meaning**: Messages are being dead-lettered after exhausting retries. Event
processing is broken.

**Immediate actions**:

1. Open the [DLQ Triage Runbook](./dlq-triage-and-replay.md)
2. Check DLQ depth:

   ```bash
   gcloud pubsub subscriptions pull {subscription}-dlq-sub \
     --project=PROJECT_ID --limit=5 --auto-ack=false --format=json
   ```

3. Check Cloud Logging for the consumer:

   ```
   resource.type="cloud_run_revision"
   jsonPayload.service="{consumer-service}"
   severity>=ERROR
   ```

4. Classify: transient vs permanent (see DLQ runbook)
5. Fix root cause → deploy → replay

**Resolution**: Alert auto-resolves when DLQ depth returns to 0.

---

### High Error Rate (Cloud Run)

**Alert**: `High error rate: {service} ({environment})`

**Meaning**: More than 5% of requests are returning 5xx for over 5 minutes.

**Immediate actions**:

1. Check if a recent deployment caused the regression:

   ```bash
   gcloud run revisions list --service={service}-{env} \
     --project=PROJECT_ID --region=REGION --limit=5
   ```

2. Check logs:

   ```
   resource.type="cloud_run_revision"
   resource.labels.service_name="{service}-{env}"
   severity>=ERROR
   ```

3. Check dependency health:
   - **Postgres**: `SELECT 1;` from Cloud SQL
   - **OpenSearch**: `curl -s http://opensearch:9200/_cluster/health`
   - **Pub/Sub**: verify topic/subscription exist
   - **Firecrawl**: check API status page

4. If caused by a bad deploy, rollback:

   ```bash
   gcloud run services update-traffic {service}-{env} \
     --project=PROJECT_ID --region=REGION \
     --to-revisions={previous-revision}=100
   ```

**Resolution**: Alert auto-closes after 1 hour of healthy error rate.

---

## Tier 2 — Warning Alerts

### High Latency (p95)

**Alert**: `High latency p95: {service} ({environment})`

**Meaning**: 95th percentile request latency exceeds 5 seconds for 15 minutes.

**Actions**:

1. Check Cloud Run metrics for CPU/memory pressure
2. Review for slow queries:

   ```
   resource.type="cloud_run_revision"
   jsonPayload.event="http_request"
   jsonPayload.duration_ms>5000
   ```

3. Check OpenSearch cluster health:

   ```bash
   curl -s http://opensearch:9200/_cluster/health?pretty
   curl -s http://opensearch:9200/_cat/nodes?v
   ```

4. Consider:
   - Increasing Cloud Run instance resources (CPU/memory)
   - Adding database indices
   - Increasing OpenSearch cluster capacity

**Resolution**: Auto-closes after 1 hour below threshold.

---

## Tier 3 — Informational (Dashboard Review)

These are not actively alerted but should be checked in daily standups:

| Signal | Where to Check | Action if Degraded |
|--------|---------------|-------------------|
| Worker error rate | Structured logs: `worker_poll_error` | Fix connector or dependency |
| Projection freshness | OpenSearch: `max(indexed_at)` | Check legal-search consumer |
| Pending run age | Postgres: oldest `status=pending` | Check worker health |

---

## Escalation Matrix

| Severity | Response Time | Escalation After |
|----------|--------------|-----------------|
| Critical | 15 minutes | 1 hour without resolution |
| Warning | 1 hour | 4 hours without resolution |
| Info | Next business day | — |

## Related Resources

- [SLI/SLO definitions](../adr/sli-slo-definitions.md)
- [DLQ triage runbook](./dlq-triage-and-replay.md)
- [Connector worker runbook](./connector-worker-operations.md)
- [Scraping run health dashboard](./scraping-run-health-dashboard.md)
- [Terraform alert policies](../../infra/terraform/gcp/runtime_stack/monitoring.tf)
