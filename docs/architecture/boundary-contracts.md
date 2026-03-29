# Boundary Contracts

## Overview

Evidara has two major handoff boundaries between its runtime domains. These boundaries are defined by explicit contracts and enforced through schema validation and event-driven communication.

## Boundary 1: platform-control → document-intelligence

### What crosses this boundary

| Direction | Payload | Mechanism |
|-----------|---------|-----------|
| platform-control → document-intelligence | `raw_artifact.available` event | Async (Pub/Sub) |
| document-intelligence → platform-control | Processing status updates | Async (Pub/Sub) or callback API |

### Contract: `raw_artifact.available`

When platform-control completes a run and stores a raw artifact in object storage, it emits a `raw_artifact.available` event.

**The event must include:**

- `source_id` — the source that produced the artifact
- `source_version_id` — the specific version
- `run_id` — the run that produced the artifact
- `artifact_id` — unique ID of the raw artifact
- `storage_path` — object storage location of the raw artifact
- `content_type` — MIME type or format hint
- `metadata` — any additional metadata from the run

**Ownership of IDs at this boundary:**

- `source_id`, `source_version_id`, `run_id`: owned by platform-control
- `artifact_id`: assigned by platform-control, carried through to document-intelligence
- `document_id`: assigned by document-intelligence upon processing

### Principles

- platform-control does not know or care about the internal processing steps of document-intelligence.
- document-intelligence does not manage sources, versions, or approvals.
- The raw artifact in object storage is the physical handoff point.
- Lineage is maintained through IDs: every canonical document traces back to a run, source version, and source.

---

## Boundary 2: document-intelligence → legal-search

### What crosses this boundary

| Direction | Payload | Mechanism |
|-----------|---------|-----------|
| document-intelligence → legal-search | `document.processed` event | Async (Pub/Sub) |
| legal-search (internal) | Reads canonical truth from Delta | Sync (read) |

### Contract: `document.processed`

When document-intelligence produces a canonical document (and optionally sections, citations), it emits a `document.processed` event.

**The event must include:**

- `document_id` — the canonical document ID
- `source_id` — traceability back to source
- `run_id` — traceability back to run
- `artifact_id` — traceability back to raw artifact
- `version` — processing version or schema version
- `canonical_path` — Delta table path or location of canonical record

**Ownership of IDs at this boundary:**

- `document_id`, `section_id`, `citation_id`: owned by document-intelligence
- `source_id`, `run_id`, `artifact_id`: passed through from platform-control

### Boundary Principles

- document-intelligence writes canonical truth to Delta. This is the source of truth.
- legal-search reads from Delta to build OpenSearch serving projections. OpenSearch is never the source of truth.
- The `document.processed` event triggers indexing, but legal-search can also perform full reindexes independently.
- legal-search never writes back to Delta or modifies canonical truth.

---

## Contract Evolution

- **Contracts are minimal and versioned.** Start with the smallest viable contract and expand incrementally.
- **IDs and ownership are stabilized first.** ID formats and ownership rules are defined early and change rarely.
- **Payload shapes may evolve.** Fields may be added to events and schemas over time, following backwards-compatible patterns (additive changes only).
- **Breaking changes require an ADR.** Any change that breaks existing consumers must be documented and reviewed.
