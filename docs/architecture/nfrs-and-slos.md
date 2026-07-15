# Non-Functional Requirements & SLOs

## Overview

This page captures **platform-level** expectations for reliability and performance. Team-level SLOs should be refined per environment as traffic and SLAs firm up.

## Latency (user-facing)

| Surface | Target (initial) | Notes |
|---------|------------------|--------|
| Search (`legal-search` BFF → OpenSearch) | p95 under 2s for typical queries | Depends on index size, query complexity, and region. |
| Document detail (BFF → OpenSearch metadata + Document Service body) | p95 under 3s | Dominated by Docling payload size and Document Service implementation (SQL gateway vs dedicated service). |
| platform-control operational APIs | p95 under 1s for CRUD-style actions | Operator-facing (React Admin); avoid long work on the request thread. |

## Availability

- **legal-search** and **platform-control** run as Kubernetes Deployments on the self-hosted Hetzner k3s cluster ([ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md)) with health checks and rolling updates. The cluster is **single-node**, so node loss is an outage: availability targets are best-effort, not HA.
- **document-intelligence** jobs are **asynchronous**; availability is measured as successful pipeline completion and timely event emission, not HTTP uptime of a single long-lived server.

## Durability

- **Postgres** (platform-control): self-hosted CloudNativePG; RPO/RTO follow the cluster's own backup configuration — self-managed, not a provider SLA.
- **Delta / object storage**: Immutable artifacts and published surfaces on in-cluster MinIO; recovery procedures tie to [Disaster Recovery](disaster-recovery.md).

## Observability

- **Correlation IDs** — Standardize on `X-Correlation-Id` (while still accepting `X-Request-ID`) across `platform-control`, `legal-search/api`, and `document-intelligence` HTTP surfaces; always echo both headers in responses.
- **Structured logs** — Emit request logs with stable fields (`service`, `method`, `path`, `status_code`, `duration_ms`, `correlation_id`) and include domain IDs (`tenant_id`, `corpus_id`, `document_id`, `run_id`) where applicable.
- **Metrics** — Request rates, error rates, and latency histograms per service; processing-job success/failure and NATS JetStream consumer health (redelivery counts, DLQ depth) for `document-intelligence`.

## Review cadence

Revisit this page when onboarding a new region, changing the Document Service topology, or signing external SLAs.
