# First Vertical Slice

## Goal

The smallest end-to-end flow that proves the architecture works: a single source can be configured, run, bundled, processed, indexed, and searched.

## Frozen scope

For `ws-00-contract-sync`, the first slice is frozen to the narrowest currently credible path:

- one Firecrawl-backed source family
- one primary HTML document artifact per bundle for the happy path
- Swiss public legal content as the working reference domain for the first searchable slice
- `tenant_id`, `corpus_id`, and `scope_type` carried through source-version acquisition config and bundle/event provenance for now, not first-class corpus CRUD yet

The current repo already contains secondary RIS-style XML coverage in `document-intelligence`, but that path is regression coverage, not the required deployment path for M4.

## End-to-End Steps

```text
1. Create source and freeze scope metadata for the run → platform-control
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

`[~]` below means the repo already has partial scaffolding or a local implementation, but production runtime wiring is still pending.

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

- [~] Source CRUD API exists; corpus and tenant scope are still frozen through acquisition config and bundle provenance rather than first-class control-plane CRUD
- [x] Source version API and approval flow
- [x] Run lifecycle API
- [x] Snapshot, artifact, and bundle-manifest registration
- [x] `artifact_bundle.available` event emission
- [x] `document.processing_status.updated` consumer and read-model persistence

### document-intelligence

- [~] `artifact_bundle.available` processing entrypoints exist, with runtime consumer scaffolding landed; deployment wiring is still pending
- [x] Bundle-manifest and raw-artifact reader
- [x] Canonical `Document` and `Section` writers
- [x] Published surfaces for documents, sections, and processing manifests
- [x] `document.processing_status.updated` event emission
- [x] `document.processed` event emission

### legal-search

- [~] `document.processed` consumer
- [ ] Projection builder from published DI surfaces
- [x] OpenSearch index and alias setup
- [x] Minimal projection manifest/history record
- [x] Search and detail API
- [~] Minimal frontend exists, but it is still mock-backed rather than connected to the live BFF

### contracts

- [x] `ArtifactBundleManifest` schema
- [x] `ProcessingManifest` schema
- [x] `artifact_bundle.available` event schema
- [x] `document.processed` event schema
- [x] Search and control OpenAPI specs

### infra

- [x] GCS bucket for raw artifacts and bundle manifests
- [x] Pub/Sub topics and subscriptions
- [~] Databricks workspace and published-surface scaffolding exists in Terraform and bundle files, but deployment/runtime wiring is still pending
- [ ] OpenSearch cluster
- [x] OpenSearch alias cutover path
- [~] Cloud Run services

## Success criteria

1. An approved source version can be run.
2. A bundle manifest is written with at least one primary artifact and frozen scope/provenance fields.
3. `artifact_bundle.available` is emitted and consumed.
4. DI emits `document.processing_status.updated` and platform-control can observe it.
5. DI publishes one canonical document revision and sections.
6. `document.processed` is emitted with exact published refs.
7. `legal-search` indexes the document through an alias-backed index and returns it in search.
