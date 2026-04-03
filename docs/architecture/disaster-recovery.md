# Disaster Recovery

## Overview

Recovery priorities: **restore operator control**, **restore search serving**, then **replay or rebuild** canonical data and indices as needed.

## Component recovery notes

### platform-control (Postgres)

- Restore from **managed backups** (Cloud SQL PITR or equivalent).
- After restore, validate run/source state against object storage manifests before resuming ingestion.

### Object storage (raw artifacts, manifests)

- **Versioned buckets** and lifecycle rules reduce accidental loss.
- Reprocessing depends on **immutable bundle manifests** still being present; if lost, recovery requires re-acquisition from sources (operational runbook).

### document-intelligence (Delta, Databricks)

- **Unity Catalog** and workspace backups are environment-specific; document the actual backup/export procedure in Terraform / runbooks for each env.
- **Replay model**: Pub/Sub retains and DLQs should be configured so that, after outage, events can be **replayed** or bundles re-triggered without corrupting canonical identity (`document_id`, revisions).

### legal-search (OpenSearch)

- Indices are **rebuildable** from published surfaces and projection logic.
- Prefer **alias cutover** (versioned physical indices) so a rebuild does not require downtime for reads once the new index is warm.

### Document Service

- If implemented as Databricks SQL gateway, recovery follows Databricks workspace and SQL warehouse availability.
- If implemented as a dedicated service, redeploy from artifact and restore connectivity to published Delta tables or materialized JSON.

## Runbooks

- [Document Service & document detail](../runbooks/document-service-document-detail.md) — request-path failures and correlation ID tracing.
- Add environment-specific DR checklists under `docs/runbooks/` as procedures harden.

## Related

- [Storage Model](storage-model.md)
- [Data Lifecycle](data-lifecycle.md)
