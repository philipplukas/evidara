# ADR-0003: Storage Strategy

## Status

Accepted

## Date

2026-03-28

## Context

Different parts of the platform have fundamentally different storage needs. We need a storage strategy that matches each component's access patterns, consistency requirements, and scale characteristics.

## Decision

Use four storage technologies:

| Technology | Purpose | Used by |
|------------|---------|---------|
| **Postgres** (Cloud SQL) | Operational control-plane data | platform-control |
| **Object Storage** (GCS) | Raw artifacts and large immutable blobs | platform-control, document-intelligence |
| **Delta Tables** (Databricks) | Canonical structured truth | document-intelligence |
| **OpenSearch** | Search-serving projections | legal-search |

## Rationale

- **Postgres** provides transactional consistency for operational workflows (source management, approvals, runs). It excels at OLTP workloads with frequent small reads and writes.
- **Object Storage** is the natural fit for large, immutable files (PDFs, HTML snapshots). It is cost-effective and durable.
- **Delta** provides ACID transactions on data lake storage, schema evolution, and time travel. It is purpose-built for the batch processing and analytical queries that document intelligence requires.
- **OpenSearch** provides full-text search, relevance ranking, and faceted filtering optimized for user-facing search experiences.

## Key Constraint

**Canonical truth is in Delta. OpenSearch contains derived projections only.** If OpenSearch is lost, it is rebuilt from Delta. The reverse is never true.

## Consequences

- Each component uses its designated storage. No component reads another component's storage directly.
- Data flows between storage layers through contracts (events and APIs).
- The team must maintain expertise in four storage technologies.
- Infrastructure provisioning must cover all four.
