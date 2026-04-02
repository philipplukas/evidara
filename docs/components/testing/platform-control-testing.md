# Platform Control Testing

## Scope

Testing strategy for the platform-control component, which owns:

- Jurisdictions and authorities (reference data)
- Seed sources
- Source registry
- Source versions
- Runs
- Approvals
- Raw artifact metadata handling

---

## Minimal Tests for MVP

### Unit Tests

#### State transition tests

- Run lifecycle: `pending` → `running` → `completed` / `failed`
- Approval workflow: `pending` → `approved` / `rejected`
- Invalid transitions are rejected (e.g., `completed` → `pending`)

#### Validation tests

- Source config schemas: valid configs pass, invalid configs are rejected
- Acquisition spec schemas: valid Firecrawl-backed configs pass, invalid configs are rejected
- Extractor profile references are validated at source-version creation time
- Reference-data seed files validate before any write is attempted
- Required fields for source creation: name, jurisdiction, authority
- Source version requires a source to exist

#### Provider integration tests

- Firecrawl request mapping preserves source, version, and run identity
- Webhook signature verification rejects tampered payloads
- Webhook dedupe logic treats repeated deliveries as idempotent
- Captured-resource normalization produces stable provider-neutral rows
- GCS artifact storage writes deterministic object paths
- Pub/Sub event publishing emits the expected `raw_artifact.available` envelope
- Seed loading is idempotent and supports dry-run mode

### Contract Tests

- `RawArtifactEnvelope` payloads conform to JSON Schema
- `raw_artifact.available` event payload conforms to event schema
- All required fields are present: `source_id`, `source_version_id`, `run_id`, `artifact_id`, `storage_path`, `content_type`
- Fixture webhook payloads map to internal models without dropping required lineage fields

### Workflow Tests

- Approval workflow: create source → create version → approve version
- Run creation: approved source version → create run → run completes → artifact metadata recorded
- Run failure: run transitions to `failed` when processing errors occur
- Preview workflow: create source → create version → preview run → captured resources recorded → operator can review summary
- Webhook replay workflow: same Firecrawl callback delivered twice → one artifact set persisted

### Smoke Tests

- One source family end-to-end: register source → create version → approve → trigger run → verify artifact metadata is recorded
- Health check endpoint returns 200
- Firecrawl-backed preview run using stubbed provider responses reaches a terminal state

---

## Drift Checks

| Check | What it catches |
|-------|----------------|
| Artifact count not unexpectedly zero | Source has stopped producing |
| Content type still expected | Source format changed |
| Empty output detection | Run completed but produced nothing |
| Artifact size sanity thresholds | Artifacts are suspiciously small or large |
| Captured-resource count suddenly collapses | Discovery or filtering logic changed unexpectedly |

---

## Confidence Goal

These tests should answer:

- **Can we trust source lifecycle and run tracking?** — State transitions are correct, IDs are stable, runs produce artifacts.
- **Can we detect when a source has started failing?** — Drift checks catch silent failures.
- **Can we safely rely on provider webhooks?** — Signature verification and idempotency keep callbacks trustworthy.

---

## What NOT to Overbuild Early

- Do not build comprehensive CRUD tests for every entity — focus on state transitions and boundaries
- Do not test database query performance — correctness first
- Do not build UI tests for Retool admin (it does not exist yet)
- Do not test every possible source configuration — test the schema validation, trust that the schema covers the rest
- Do not build sophisticated source health monitoring — simple artifact count and content type checks are enough for MVP
- Do not call live Firecrawl in CI — stub provider calls and use fixture webhook payloads instead

---

## Later Expansion

| Phase | Addition |
|-------|---------|
| Post-MVP | Multi-source family smoke tests |
| Post-MVP | Integration tests with real database |
| Later | Approval notification tests |
| Later | Concurrent run behavior tests |
| Later | Source health trend monitoring |
