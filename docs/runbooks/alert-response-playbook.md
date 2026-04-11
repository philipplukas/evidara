# Alert Response Playbook

Owner: Platform team
Last reviewed: 2026-04-11
Last verified: Not yet verified
Applies to: dev, staging, prod

## Overview

This playbook documents how to respond to automated alerts from the Evidara
monitoring stack. Each alert links to a specific section below.

For SLI/SLO definitions, see [docs/adr/sli-slo-definitions.md](../adr/sli-slo-definitions.md).

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
