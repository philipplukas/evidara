# SLI/SLO Definitions

Status: Accepted
Date: 2026-04-03
Applies to: dev, staging, prod

## Context

As Evidara moves toward production readiness, we need explicit service-level
indicators (SLIs) and objectives (SLOs) to drive alerting, capacity planning,
and incident response priorities.

These definitions cover the three core runtime services (platform-control,
document-intelligence, legal-search) and the event-driven pipelines connecting
them.

## Service-Level Indicators (SLIs)

### API Availability

| SLI | Measurement | Source |
|-----|-------------|--------|
| **API success rate** | % of requests returning 2xx/4xx (not 5xx) | Cloud Run metrics |
| **API latency p95** | 95th percentile response time | Cloud Run metrics |
| **API latency p99** | 99th percentile response time | Cloud Run metrics |

*Applies to*: platform-control-api, legal-search-api

### Event Pipeline Freshness

| SLI | Measurement | Source |
|-----|-------------|--------|
| **Event processing latency** | Time from event publish to consumer ack | Cloud Logging (structured logs) |
| **DLQ depth** | Number of unacked messages in DLQ subscriptions | Pub/Sub metrics |
| **End-to-end latency** | Time from `artifact_bundle.available` to search document indexed | Structured log correlation |

*Applies to*: DI consumer, legal-search projection consumer, platform-control status consumer

### Worker Health

| SLI | Measurement | Source |
|-----|-------------|--------|
| **Pending run age** | Max age of oldest pending run | Custom query / structured logs |
| **Worker dispatch rate** | Runs dispatched per minute | Structured logs (`worker_poll_cycle`) |
| **Worker error rate** | % of poll cycles with errors | Structured logs (`worker_poll_error`) |

*Applies to*: platform-control-worker

### Data Freshness

| SLI | Measurement | Source |
|-----|-------------|--------|
| **Search index freshness** | Age of most recent projected document | OpenSearch query |
| **Projection history gap** | Time since last projection event | OpenSearch / structured logs |

*Applies to*: legal-search (OpenSearch)

## Service-Level Objectives (SLOs)

### Tier 1 — Critical (alert immediately)

| SLO | Target | Window | Alert Threshold |
|-----|--------|--------|----------------|
| API success rate | ≥ 99% | 5 min rolling | < 95% for 5 min |
| DLQ depth | 0 messages | Instantaneous | > 0 for 15 min |
| Worker pending run age | < 5 min | Instantaneous | > 10 min |

### Tier 2 — Important (alert within 30 min)

| SLO | Target | Window | Alert Threshold |
|-----|--------|--------|----------------|
| API latency p95 | < 2s | 15 min rolling | > 5s for 15 min |
| End-to-end processing latency | < 10 min | 30 min rolling | > 30 min |
| Search index freshness | < 30 min | 30 min rolling | > 60 min |

### Tier 3 — Informational (daily review)

| SLO | Target | Window |
|-----|--------|--------|
| API latency p99 | < 5s | 1 hour rolling |
| Worker error rate | < 5% | 1 hour rolling |
| Projection history gap | < 1 hour | 1 hour rolling |

## Alert Routing

| Tier | Channel | Response Time |
|------|---------|--------------|
| Tier 1 | Email + Slack `#evidara-alerts` | Within 15 min |
| Tier 2 | Slack `#evidara-alerts` | Within 1 hour |
| Tier 3 | Dashboard review | Next business day |

## Monitoring Stack

Since the move to the self-hosted Hetzner runtime (ADR-0029), the signal sources below
replaced every GCP one. See [ADR-0032](0032-pipeline-observability.md).

- **Metrics source**: Prometheus (kube-prometheus-stack) scraping a `/metrics` endpoint
  on every service, plus the NATS JetStream exporter
- **Logs**: structured JSON from all services (`kubectl logs`)
- **Alerting**: Alertmanager, rules in `infra/hetzner/observability/alerts.yaml`
- **Dashboards**: Grafana — the **pipeline funnel** is the primary one
- **Notification**: Alertmanager receivers. **No external receiver is configured by
  default** — wiring Slack is a one-value change, see
  [docs/setup/hetzner-observability.md](../setup/hetzner-observability.md)

> The SLIs in the tables above still name Cloud Run / Pub/Sub metrics as their source.
> The *targets* remain valid; the sources are being ported to their Prometheus
> equivalents. `documents-read` alias resolution, search zero-result rate, and the
> pipeline funnel counters are live today (ADR-0032).

### Retired (GCP)

- Google Cloud Monitoring (Cloud Run, Pub/Sub built-in metrics), Cloud Logging,
  Cloud Monitoring alert policies (Terraform-managed)

## Related Resources

- [Alert response playbook](../runbooks/alert-response-playbook.md)
- [DLQ triage runbook](../runbooks/dlq-triage-and-replay.md)
- [Connector worker runbook](../runbooks/connector-worker-operations.md)
- [Terraform alert policies](../../infra/terraform/gcp/runtime_stack/monitoring.tf)
