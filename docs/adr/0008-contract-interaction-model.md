# ADR-0008: Contract Interaction Model

## Status

Accepted

## Date

2026-03-29

## Context

Evidara needs a contract model that keeps `platform-control`, `document-intelligence`, and `legal-search` decoupled while still supporting:

- heterogeneous acquisition sources
- source-specific and jurisdiction-specific processing
- replay and auditability
- OpenSearch as a serving projection only
- tenant and corpus boundaries for public and private data

The earlier placeholder contracts were too narrow around single raw artifacts and did not capture bundle semantics, revisioning, or published-surface refs.

## Decision

- Replace the old single-artifact handoff with `ArtifactBundleManifest` and `artifact_bundle.available`.
- Use a shared CloudEvents-aligned event envelope with stable `event_type` and explicit `event_version`.
- Model lineage through a reusable `provenance` block.
- Treat `document_id` as the stable logical identity within a corpus.
- Treat `processing_manifest_id` as the immutable processing-result identity.
- Add `document_revision` as the monotonic downstream ordering field.
- Have `document.processed` point to exact immutable published-surface refs rather than embedding full payloads or internal Delta paths.
- Store manifests as immutable JSON objects and mirror searchable metadata into component-owned query surfaces where needed.
- Reuse Unity Catalog lineage for DI-internal table and job lineage rather than inventing parallel cross-component contracts for every internal edge.
- Keep `legal-search` responsible for OpenSearch projections and projection history.
- Reuse OpenSearch versioned physical indices and aliases for rebuild and cutover workflows.
- Model public data with a reserved non-null tenant such as `tenant_public`.

## Consequences

- `platform-control` owns tenants, corpora, sources, source versions, runs, snapshots, artifacts, and bundle manifests.
- `document-intelligence` owns parsing, canonicalization, revisions, processing manifests, and published surfaces.
- `legal-search` consumes DI publication events and builds OpenSearch projections without owning canonical truth.
- Breaking event changes use a higher `event_version`; additive changes stay within the current version.
- Downstream consumers can replay deterministically from exact immutable refs.
- Contracts stay focused on business identity, lineage, and lifecycle semantics; platform-native lineage and index-lifecycle features do the rest.
