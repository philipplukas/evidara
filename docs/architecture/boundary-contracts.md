# Boundary Contracts

## Overview

Evidara has two major runtime handoff boundaries:

1. `platform-control` ↔ `document-intelligence`
2. `document-intelligence` → `legal-search`

Each boundary has a different purpose:

- `platform-control` hands off immutable acquisition input and receives operational status back
- `document-intelligence` publishes canonical-ready document revisions for downstream serving

## Boundary 1: platform-control ↔ document-intelligence

### What crosses this boundary

| Direction | Payload | Mechanism |
|-----------|---------|-----------|
| platform-control → document-intelligence | `artifact_bundle.available` event | Async (Pub/Sub) |
| platform-control → document-intelligence | reference snapshot sets | published file or dataset surface |
| document-intelligence → platform-control | `document.processing_status.updated` event | Async (Pub/Sub) |

### Core contract objects

- `ArtifactBundleManifest`
- `artifact_bundle.available`
- `document.processing_status.updated`

### Meaning of the handoff

When `platform-control` has durably stored one upstream snapshot and its sibling artifacts, it emits `artifact_bundle.available`.

The event carries:

- stable lineage via `provenance`
- `bundle_manifest_id`
- `source_snapshot_id`
- source-origin and trust facts
- a typed `bundle_manifest_ref`

The referenced `ArtifactBundleManifest` carries the frozen processing inputs:

- `source_defaults`
- `parser_hints`
- optional `di_overrides`
- `reference_context`
- artifact inventory and storage refs

### Boundary principles

- `platform-control` owns source lifecycle, corpora, approvals, runs, and acquisition state.
- `document-intelligence` owns interpretation, normalization, and canonical truth.
- `platform-control` may freeze DI hints and override refs, but it does not choose DI implementation classes.
- `document-intelligence` must not read `platform-control`'s operational database directly.
- `document-intelligence` reports progress via status events rather than by mutating `platform-control` state directly.

### Clear ownership examples

- A website changes pagination from `page=2` to cursor tokens:
  This is `platform-control` work. Update connector config, sync strategy, checkpointing, and run behavior.
- A Swiss canton PDF needs custom heading detection:
  This is `document-intelligence` work. Update the jurisdiction or source profile logic in DI.
- A source should now default into a different corpus:
  This is `platform-control` work. Corpus assignment belongs to source governance.
- Two artifacts from the same upstream snapshot should be combined before canonicalization:
  This is `document-intelligence` work. Bundle interpretation belongs to DI once the immutable bundle exists.

## Boundary 2: document-intelligence → legal-search

### What crosses this boundary

| Direction | Payload | Mechanism |
|-----------|---------|-----------|
| document-intelligence → legal-search | `document.processed` event | Async (Pub/Sub) |
| document-intelligence → legal-search | `document.withdrawn` event | Async (Pub/Sub) |
| legal-search | reads published canonical surfaces referenced by the event | Sync (read) |

### Core contract objects

- `ProcessingManifest`
- `Document`
- `Section`
- `document.processed`
- `document.withdrawn`

### Meaning of `document.processed`

`document.processed` is emitted once one logical document revision becomes canonical-ready.

The event carries:

- stable `document_id`
- monotonic `document_revision`
- immutable `processing_manifest_id`
- `provenance`
- lifecycle state
- exact immutable refs to `published_documents`, `published_sections`, and the `ProcessingManifest`

The event does **not** embed the full document body and does **not** expose arbitrary internal Delta table names or paths.

### Published surfaces

`document-intelligence` owns internal bronze/silver organization, but downstream consumers read only published contract surfaces such as:

- `published_documents`
- `published_sections`
- `processing_manifests`

The event points at those surfaces through `dataset_ref` and `manifest_ref`, which keeps internal DI modeling evolvable without breaking `legal-search`.

### Boundary principles

- `document-intelligence` owns canonical truth and document revisioning.
- `legal-search` owns all OpenSearch mappings, aliases, indexing jobs, and projection logic.
- `legal-search` must not treat OpenSearch as a source of truth.
- `legal-search` must not query arbitrary internal DI tables; it reads only published surfaces.
- `document.processed` is emitted per document, not per bundle.

### Supersession and withdrawal

- Processing supersession flows through `document.processed` with a higher `document_revision`.
- Legal lifecycle changes such as `superseded` or `repealed` also flow through `document.processed`.
- True public-search removal flows through `document.withdrawn`.

## Standards Vs Domain Contracts

Use standards and managed capabilities where they fit, but keep business semantics explicit:

- Event metadata should stay CloudEvents-aligned.
- Bundle and processing manifests should be immutable JSON objects referenced through `manifest_ref`.
- Searchable manifest metadata should be mirrored into component-owned query surfaces rather than encoded in Hive-style path semantics.
- Databricks / Unity Catalog should provide DI-internal lineage for jobs, tables, and published views.
- OpenSearch aliases and versioned physical indices should provide search cutover and rebuild mechanics.

Evidara-specific contracts still need to own:

- `tenant_id`, `corpus_id`, and scope boundaries
- source/version/run/snapshot/artifact lineage across components
- stable `document_id`
- immutable `processing_manifest_id`
- monotonic `document_revision`
- resolution-policy and withdrawal semantics

## Contract Evolution

- Contracts are additive within a version.
- Event names stay stable; `event_version` carries the major version.
- Breaking changes require a new version and an ADR.
- New fields should be optional first unless every producer and consumer changes together.
- Example payloads in `contracts/examples/` are part of the contract surface and should evolve with the schema.
