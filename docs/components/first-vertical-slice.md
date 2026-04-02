# First Vertical Slice

## Goal

The smallest end-to-end flow that proves the architecture works: a single source can be configured, run, bundled, processed, indexed, and searched.

## End-to-End Steps

```text
1. Create source and corpus        → platform-control
2. Create source version           → platform-control
3. Approve source version          → platform-control
4. Trigger run                     → platform-control
5. Write artifacts + bundle manifest → object storage (GCS)
6. Emit artifact_bundle.available  → Pub/Sub
7. Process bundle                  → document-intelligence
8. Publish documents, sections, processing manifest → DI published surfaces
9. Emit document.processing_status.updated → Pub/Sub
10. Emit document.processed        → Pub/Sub
11. Index into OpenSearch          → legal-search
12. Search and view document       → legal-search UI/API
```

## What Must Exist

## Parallel execution tracks

The vertical slice can progress in parallel with clear handoff boundaries:

- **Track A — Platform Control handoff producer**
  - deliver source/version/run and artifact registration
  - emit `artifact_bundle.available`
- **Track B — Document Intelligence processor**
  - consume `artifact_bundle.available`
  - publish canonical refs and emit `document.processed`
- **Track C — Legal Search serving projection**
  - consume `document.processed`
  - upsert OpenSearch projection and expose search/detail
- **Track D — Infra and runtime plumbing**
  - provision buckets, topics/subscriptions, Cloud Run jobs/services, OpenSearch
- **Track E — Contracts and compatibility**
  - keep schema/event/OpenAPI compatibility checks green as tracks evolve

### platform-control

- [ ] Source and corpus CRUD API
- [ ] Source version API and approval flow
- [ ] Run lifecycle API
- [ ] Snapshot, artifact, and bundle-manifest registration
- [ ] `artifact_bundle.available` event emission
- [ ] `document.processing_status.updated` consumer and read-model persistence

### document-intelligence

- [ ] `artifact_bundle.available` consumer
- [ ] Bundle-manifest and raw-artifact reader
- [ ] Canonical `Document` and `Section` writers
- [ ] Published surfaces for documents, sections, and processing manifests
- [ ] `document.processing_status.updated` event emission
- [ ] `document.processed` event emission

### legal-search

- [ ] `document.processed` consumer
- [ ] Projection builder from published DI surfaces
- [ ] OpenSearch index and alias setup
- [ ] Minimal projection manifest/history record
- [ ] Search and detail API
- [ ] Minimal frontend

### contracts

- [x] `ArtifactBundleManifest` schema
- [x] `ProcessingManifest` schema
- [x] `artifact_bundle.available` event schema
- [x] `document.processed` event schema
- [x] Search and control OpenAPI specs

### infra

- [ ] GCS bucket for raw artifacts and bundle manifests
- [ ] Pub/Sub topics and subscriptions
- [ ] Databricks workspace and published surface access
- [ ] OpenSearch cluster
- [ ] OpenSearch alias cutover path
- [ ] Cloud Run services

## Success criteria

1. An approved source version can be run.
2. A bundle manifest is written with at least one primary artifact.
3. `artifact_bundle.available` is emitted and consumed.
4. DI emits `document.processing_status.updated` and platform-control can observe it.
5. DI publishes one canonical document revision and sections.
6. `document.processed` is emitted with exact published refs.
7. `legal-search` indexes the document through an alias-backed index and returns it in search.
