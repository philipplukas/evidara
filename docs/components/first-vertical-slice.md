# First Vertical Slice

## Goal

The smallest end-to-end flow that proves the architecture works: a single source can be registered, run, processed, indexed, and searched.

## End-to-End Steps

```text

1. Create source             →  platform-control
2. Create source version     →  platform-control
3. Trigger run               →  platform-control
4. Write raw artifact        →  object storage (GCS)
5. Emit raw_artifact.available →  Pub/Sub
6. Process raw artifact      →  document-intelligence
7. Produce canonical document →  Delta table
8. Emit document.processed   →  Pub/Sub
9. Index into OpenSearch     →  legal-search
10. Search and view document →  legal-search UI/API

```

## What Must Exist

### platform-control

- [ ] Source CRUD API (create, read)
- [ ] Source version CRUD API (create, read)
- [ ] Run lifecycle API (trigger, status)
- [ ] Raw artifact upload/registration
- [ ] `raw_artifact.available` event emission
- [ ] Postgres schema for sources, versions, runs

### document-intelligence

- [ ] `raw_artifact.available` event consumer
- [ ] Raw artifact reader (from GCS)
- [ ] Minimal document parser
- [ ] Canonical Document writer (to Delta)
- [ ] `document.processed` event emission

### legal-search

- [ ] `document.processed` event consumer
- [ ] Delta-to-OpenSearch projection builder
- [ ] OpenSearch index with document mapping
- [ ] Search API endpoint
- [ ] Document detail API endpoint
- [ ] Minimal search UI page
- [ ] Minimal document detail UI page

### contracts

- [ ] `raw_artifact.available` event schema
- [ ] `document.processed` event schema
- [ ] `RawArtifactEnvelope` schema
- [ ] `Document` schema
- [ ] platform-control OpenAPI (source, version, run endpoints)
- [ ] legal-search OpenAPI (search, detail endpoints)
- [ ] ID conventions documented

### infra

- [ ] GCS bucket for raw artifacts
- [ ] Cloud SQL instance
- [ ] Pub/Sub topics
- [ ] Cloud Run services
- [ ] Databricks workspace and storage

## Success Criteria

The vertical slice is complete when:

1. A source can be created via API
2. A source version can be registered
3. A run can be triggered
4. A raw artifact appears in object storage
5. The `raw_artifact.available` event fires
6. Document-intelligence processes the artifact
7. A canonical document row appears in Delta
8. The `document.processed` event fires
9. The document appears in OpenSearch
10. A user can search for and view the document in the UI

## This is Milestone M4

This vertical slice is the first true end-to-end milestone. Milestones M1–M3 build the pieces. M4 connects them.

## Implementation Order

1. First: complete contracts (schemas, events, APIs)
2. Then: build each component's minimal functionality
3. Then: connect via events and test end-to-end
4. Last: verify the UI shows the result

Only start implementation code after contracts are stable for this slice.
