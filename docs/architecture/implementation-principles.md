# Implementation Principles

Use these principles when adding or changing Evidara contracts, handoff surfaces, and cross-component interactions.

## Core Principles

1. Start from business transitions, not service boundaries.
2. Define ownership before schema shape.
3. Design replay and failure handling before optimizing the happy path.
4. Use synchronous APIs for control-plane and query interactions.
5. Use events for long-running, replayable workflow progression.
6. Keep canonical truth separate from serving projections.
7. Prefer exact immutable refs over oversized payload events.

## Standards Before Reinvention

Reuse standards and platform capabilities where they reduce bespoke infrastructure:

- Use JSON Schema and OpenAPI as the contract-definition formats.
- Keep the event envelope CloudEvents-aligned instead of inventing custom metadata rules per event.
- Use the immutable processing manifests plus Delta table history for table and job lineage inside document-intelligence; there is no external catalog service (the runtime is self-hosted — see [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md)).
- Add OpenLineage only if cross-platform lineage becomes a real requirement that manifests and table history cannot cover alone.
- Use OpenSearch versioned indices and aliases for rebuild and cutover workflows.

Do not try to push all of that metadata into business payloads. Contracts should capture:

- ownership
- lifecycle transitions
- lineage that crosses component boundaries
- stable identities
- published-surface refs needed for replay

## Manifest And Published-Surface Principles

- Store manifests as immutable JSON objects.
- Mirror searchable manifest metadata into component-owned query surfaces instead of encoding semantics into folder paths.
- Publish stable downstream dataset surfaces such as `published_documents`, `published_sections`, and `processing_manifests`.
- Events should point to exact immutable published refs, not arbitrary internal table names.

## Evolution Principles

- Make additive changes within a version whenever possible.
- Use a new major version for breaking changes.
- Keep override mechanisms explicit and rare.
- Favor one real boundary pattern over temporary shortcuts.
