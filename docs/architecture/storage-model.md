# Storage Model

## Overview

Evidara uses four storage technologies, each chosen for a specific access and change pattern. No single database is used for everything.

## Storage Technologies

### Postgres (Cloud SQL)

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

---

### Object Storage (Cloud Storage / GCS)

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

---

### Delta Tables (Databricks)

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
- Native integration with Databricks processing pipelines
- Optimized for both batch processing and analytical queries

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
