# Disaster Recovery

## Overview

Recovery priorities: **restore operator control**, **restore search serving**, then **replay or rebuild** canonical data and indices as needed.

The runtime is a **self-hosted single-node k3s cluster** ([ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md)): every store below is self-managed, and node loss is a full outage. There is no managed-service SLA to fall back on — backup and restore are the operator's responsibility.

## Component recovery notes

### platform-control (Postgres)

- Restore from **CloudNativePG backups** (in-cluster Postgres operator); PITR depends on the cluster's configured backup target.
- After restore, validate run/source state against object storage manifests before resuming ingestion.

### Object storage (raw artifacts, manifests)

- MinIO in-cluster; **bucket versioning** and lifecycle rules reduce accidental loss.
- Reprocessing depends on **immutable bundle manifests** still being present; if lost, recovery requires re-acquisition from sources (operational runbook).

### document-intelligence (Delta on MinIO)

- Canonical Delta tables live on MinIO and are written by the pure-Python `deltalake` sink. Their durability is MinIO's durability — back up the bucket; there is no separate catalog or workspace to restore.
- **Replay model**: NATS JetStream stream retention, redelivery, and the app-level DLQ subject should be configured so that, after outage, events can be **replayed** or bundles re-triggered without corrupting canonical identity (`document_id`, revisions).

### legal-search (OpenSearch)

- Indices are **rebuildable** from published surfaces and projection logic.
- Prefer **alias cutover** (versioned physical indices) so a rebuild does not require downtime for reads once the new index is warm.

### Document Service

- Runs as a Deployment in the cluster: redeploy from the image and restore connectivity to the published Delta tables on MinIO.
- If SQL-gateway reads are used, they go through in-cluster **Trino** over the **Nessie** catalog; recovery there is a redeploy plus catalog availability, and it is not a source of truth.

## Runbooks

- [Document Service & document detail](../runbooks/document-service-document-detail.md) — request-path failures and correlation ID tracing.
- Add environment-specific DR checklists under `docs/runbooks/` as procedures harden.

## Related

- [Storage Model](storage-model.md)
- [Data Lifecycle](data-lifecycle.md)
