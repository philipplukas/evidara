# Storage Model

## Overview

Evidara uses four storage technologies, each chosen for a specific access and change pattern. No single database is used for everything.

The **storage model** below (control state in Postgres, raw artifacts in an object store,
canonical truth in Delta, serving projections in OpenSearch) is stable. What changed with
[ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md) is only the **backing services**:
all four now run self-hosted in the Hetzner k3s cluster rather than as GCP/Databricks
managed services.

## Storage Technologies

### Postgres (CloudNativePG, in-cluster)

**Used by:** platform-control

**Purpose:** Operational control-plane data with transactional consistency.

**Stores:**

- Jurisdictions and authorities
- Source registry and source versions
- Run records
- Approval states
- Reference data

**Why Postgres:**

- Strong transactional guarantees for operational workflows
- Rich query capabilities for administrative and ops UIs
- Well-suited for entities with frequent reads and writes
- Familiar, well-tooled, and highly reliable

**Where it runs:** a CloudNativePG `Cluster` in the `evidara` namespace, reached over the
`evidara-pg-rw` service. Connection is a plain SQLAlchemy async engine — nothing
cloud-specific in app code.

---

### Object Storage (MinIO, S3-compatible)

**Used by:** platform-control, document-intelligence

**Purpose:** Raw artifacts and large immutable blobs.

**Stores:**

- Raw documents (PDFs, HTML snapshots, etc.)
- Downloaded source artifacts
- Processing intermediaries (if persisted)

**Why Object Storage:**

- Cost-effective for large, immutable files
- No size limits for individual objects
- Durable and highly available
- Natural fit for blob-like artifacts

**Where it runs:** MinIO in-cluster. `platform-control` writes through the `ArtifactStore`
port (`artifact_store_backend="s3"` → `S3ArtifactStore`, boto3, path-style);
`document-intelligence` reads through the `s3://` branch of `DispatchingBundleLoader`. The
port also has `local` (the code default) and `gcs` adapters, so the backend is a config
choice, not a hardcoded dependency.

---

### Delta Tables (on MinIO, via pure-Python `deltalake`)

**Used by:** document-intelligence

**Purpose:** Canonical structured truth for all processed documents.

**Stores:**

- Canonical documents
- Sections
- Citations
- Relationships
- Processing lineage and metadata

**Why Delta:**

- ACID transactions on data lake storage
- Schema evolution support
- Time travel and versioning for auditability
- Open table format — readable without a proprietary engine
- Optimized for both batch processing and analytical queries

**Where it runs:** Delta tables live on MinIO and are written by `DeltaCanonicalSink`, the
**pure-Python `deltalake`** implementation of the `CanonicalSink` port. Neither `pyspark`
nor `databricks` is a runtime dependency: the Spark sink is opt-in
(`use_spark_delta=False` by default) and is not used in the live runtime.

**Query / analytics:** the lakehouse layer in-cluster is **Nessie** (Iceberg REST catalog,
Postgres-backed) plus **Trino** for SQL access over table data on MinIO.

---

### OpenSearch

**Used by:** legal-search

**Purpose:** Serving projections optimized for search and retrieval.

**Stores:**

- Document search projections
- Section-level search documents
- Facet and filter metadata
- Pre-computed search-optimized representations

**Why OpenSearch:**

- Full-text search with relevance ranking
- Faceted search and filtering
- Low-latency queries for user-facing search UIs
- Aggregation capabilities for analytics

**Where it runs:** OpenSearch in-cluster (helm chart), fed by the always-on
NATS → projection bridge (`document-intelligence/.../jobs/projection_bridge_consumer.py`).

---

## Why Not One Database?

| Concern | Why separation matters |
|---------|----------------------|
| **Access patterns** | Operational data (frequent small reads/writes) differs fundamentally from search queries (full-text, faceted) and analytical processing (batch, columnar). |
| **Scale characteristics** | Raw artifacts can be many GB per file. Search indexes need to serve millisecond queries. Control plane data is modest in size but requires consistency. |
| **Change frequency** | Control plane data changes on every user action. Canonical truth changes on processing runs. Search projections are rebuilt from canonical truth. |
| **Failure isolation** | A search index failure should not affect source management. A processing pipeline failure should not block search serving. |
| **Technology fit** | No single database excels at OLTP, full-text search, blob storage, and batch analytics simultaneously. |

## Key Principle

**Canonical truth is separate from serving projections.**

Delta tables are the source of truth for all processed document intelligence. OpenSearch contains serving projections derived from Delta. If OpenSearch data is lost or corrupted, it can be completely rebuilt from Delta. The reverse is never true.

See also: [Implementation Principles](implementation-principles.md)
