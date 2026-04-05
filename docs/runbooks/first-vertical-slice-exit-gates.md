# First Vertical Slice Exit Gates

Owner: Platform team
Last reviewed: 2026-04-05
Last verified: 2026-04-05
Applies to: dev, staging, prod

This runbook defines the minimum verification set to declare the first Evidara vertical slice ready.

## Scope

The gate covers:

1. `platform-control` run and bundle publication
2. `document-intelligence` bundle processing and publication events
3. `legal-search` projection ingest and search/query behavior

## Required Runtime Wiring

- Runtime stack includes Cloud Run services for:
  - `platform-control-api`
  - `platform-control-worker`
  - `document-intelligence-consumer`
  - `legal-search-api`
- Pub/Sub subscriptions are present:
  - `document-intelligence-artifact-bundle-available`
  - `platform-control-document-processing-status-updated`
  - `legal-search-document-processed`
  - `legal-search-document-withdrawn`
- OpenSearch runtime target and aliases exist for the active environment.

## Exit Gate Checklist

### Gate A: Platform-Control

- Create source, source version, and run.
- Firecrawl webhook path registers raw artifacts and publishes immutable bundle manifest.
- `artifact_bundle.available` event is emitted with:
  - run/source/source-version provenance
  - `reference_snapshot_set_ref` populated in manifest `reference_context`.

### Gate B: Document-Intelligence

- `document-intelligence-consumer` receives `artifact_bundle.available`.
- Canonical `Document`, `Section`, and `ProcessingManifest` records are written.
- `document.processing_status.updated` and `document.processed` events are emitted.

### Gate C: Legal-Search

- `document.processed` is accepted by projection endpoint and upserted.
- `document.withdrawn` de-indexes/tombstones the projection.
- Projection history tracks idempotency and stale revision handling.
- Search/detail queries return the indexed document through alias-backed indices.

## Local Verification Commands

Run these checks before marking a slice validation complete:

```bash
cd evidara/legal-search/api
npm test -- --run src/modules/projections/projections.service.spec.ts
```

```bash
cd evidara/platform-control
uv run pytest tests/unit/test_firecrawl_webhook_service.py -q
```

Optionally run full component gates:

```bash
cd evidara
bash scripts/check-platform-control.sh
bash scripts/check-document-intelligence.sh
bash scripts/check-legal-search.sh
```

## Replay / Recovery Note

Current replay support is request-model based (`scope` + `replay` metadata on runs). Resumable frontier/checkpoint orchestration remains follow-on work and must be treated as an operational constraint during incident response.

