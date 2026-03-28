# Communication Model

## Overview

Evidara uses two primary communication patterns: synchronous REST APIs and asynchronous events. Each pattern serves a distinct purpose and is used at specific interaction points.

## Synchronous Communication (REST / OpenAPI)

### When to use

- A caller needs an immediate response.
- The interaction is a query (read) or a command that must confirm success/failure.
- The caller and callee are in a request-response relationship.

### Examples

| Interaction | Caller | Callee | Why sync? |
|-------------|--------|--------|-----------|
| Create a source | User / ops UI | platform-control API | User needs confirmation |
| Get run status | User / ops UI | platform-control API | User needs current state |
| Search documents | User / frontend | legal-search API | User needs search results now |
| Get document detail | User / frontend | legal-search API | User needs document content now |
| Get source versions | Internal workflow | platform-control API | Workflow needs data to proceed |

### Conventions

- All sync APIs are defined in OpenAPI specs in `contracts/api/`.
- APIs use JSON over HTTPS.
- Standard HTTP status codes are used for success, validation errors, and server errors.
- Pagination follows a consistent pattern across all APIs.

---

## Asynchronous Communication (Events / Pub/Sub)

### When to use

- A producer completes work and one or more consumers may need to react.
- The producer does not need to know about or wait for consumer processing.
- The interaction is a pipeline progression (one stage completing triggers the next).
- Decoupling is important for independent scaling and failure isolation.

### Examples

| Event | Producer | Consumer(s) | Why async? |
|-------|----------|-------------|-----------|
| `raw_artifact.available` | platform-control | document-intelligence | Processing takes time; producer doesn't wait |
| `document.processed` | document-intelligence | legal-search | Indexing is independent of processing |
| `index_update.requested` | document-intelligence or ops | legal-search | Reindex can happen independently |

### Conventions

- All event schemas are defined in `contracts/events/`.
- Events are published to Google Cloud Pub/Sub topics.
- Event payloads are JSON.
- Events include traceability IDs (source_id, run_id, artifact_id, document_id) for lineage.
- Consumers must be idempotent — receiving the same event twice should produce the same result.

---

## Component Interaction Rules

### Who may call whom

```
┌─────────────────────┐
│  platform-control   │
│                     │
│  sync API: yes      │──── event ────▶ document-intelligence
│  called by: ops UI  │
└─────────────────────┘

┌──────────────────────────┐
│  document-intelligence   │
│                          │
│  sync API: internal only │──── event ────▶ legal-search
│  called by: Databricks   │
└──────────────────────────┘

┌─────────────────┐
│  legal-search   │
│                 │
│  sync API: yes  │
│  called by: UI  │
└─────────────────┘
```

### Strict rules

1. **legal-search does NOT call document-intelligence.** It reads from Delta (or a sync from Delta) to build projections.
2. **legal-search does NOT call platform-control in the request path.** It may read reference data that has been projected/synced.
3. **document-intelligence does NOT manage sources or approvals.** That is platform-control's responsibility.
4. **platform-control does NOT process documents.** It triggers processing via events.
5. **No component reads another component's database directly.** All cross-component data flows through contracts (APIs or events).

### What interactions MUST be events

| Interaction | Why |
|-------------|-----|
| Raw artifact available → process it | Processing is long-running, async by nature |
| Document processed → index it | Indexing is decoupled from processing |
| Reindex requested → rebuild projections | Bulk operation, should not block anything |

### What interactions use APIs

| Interaction | Why |
|-------------|-----|
| CRUD on sources, versions, runs | Operational, needs immediate feedback |
| Search queries | User-facing, needs low-latency response |
| Document detail retrieval | User-facing, needs immediate content |
