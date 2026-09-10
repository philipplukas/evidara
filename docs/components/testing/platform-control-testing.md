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
- Bundle-manifest publication
- DI status and lifecycle event ingest

For the small-team scraping/acquisition quality bar and release-gate expectations, see [Scraping QA Standard](../../testing/scraping-qa-standard.md).

---

## Minimal Tests for MVP

### Unit Tests

#### API authentication

- Scoped keys: operator routes vs service ingest routes; 401 vs 403 (`tests/unit/test_auth_scopes.py`)

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
- Pub/Sub event publishing emits the expected `artifact_bundle.available` envelope after immutable handoff storage succeeds
- Seed loading is idempotent and supports dry-run mode

### Contract Tests

- `ArtifactBundleManifest` payloads conform to JSON Schema
- `artifact_bundle.available` event payload conforms to event schema
- All required lineage fields are present for the DI handoff: `source_id`, `source_version_id`, `run_id`, `source_snapshot_id`, and `bundle_manifest_ref`
- Fixture webhook payloads map to internal models without dropping required lineage fields

### Workflow Tests

- Approval workflow: create source → create version → approve version
- Run creation: approved source version → create run → run completes → artifact metadata recorded → bundle manifest published
- Run failure: run transitions to `failed` when processing errors occur
- Preview workflow: create source → create version → preview run → captured resources recorded → operator can review summary
- Webhook replay workflow: same Firecrawl callback delivered twice → one artifact set persisted

### Smoke Tests

- One source family end-to-end: register source → create version → approve → trigger run → verify artifact metadata is recorded and `artifact_bundle.available` is emitted
- Health check endpoint returns 200
- Readiness endpoint returns 200 when Postgres is reachable and 503 with dependency details when it is not
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

- **Can we trust source lifecycle and run tracking?** — State transitions are correct, IDs are stable, and successful runs publish immutable handoffs.
- **Can we detect when a source has started failing?** — Drift checks catch silent failures.
- **Can we safely rely on provider webhooks?** — Signature verification and idempotency keep callbacks trustworthy.

---

## Admin Playwright suite (`platform-control/admin/e2e/`)

Run it with `ADMIN_E2E_PORT=<free port> npm run e2e` from `platform-control/admin`
(`npm run e2e:browsers` once first). Every spec mocks platform-control with
`page.route`, so no backend, database or API key is needed — only the Next dev
server Playwright starts itself.

This is the **only** layer that sees layout, stylesheets and routing. jsdom has
none of the three, which is how a clipped ACTIONS column, a UA-beveled sort header
and a completely absent dark mode all passed `npm run check`.

### Pixel baselines (`e2e/visual.spec.ts`)

`npm run e2e:visual` compares the run-detail v2 page against the committed PNG in
`e2e/visual.spec.ts-snapshots/`. The functional suite is `npm run e2e`, which runs
`--grep-invert @visual` so the two report independently; both are invoked by
`.github/workflows/platform-control.yml`, which is what
`scripts/check-e2e-spec-coverage.sh` asserts.

**This baseline used to live under `legal-search/frontend/`** and moved here in
#913. Two costs, both measured: a PNG has no merge strategy, so two branches
touching admin layout collided on an unmergeable binary (#902, #905); and an admin
change failed a *legal-search* CI job, undiscoverable from the admin tree (#895).
A surface owns its own baselines, its own ledger and its own CI job.

**Zero pixel tolerance.** `playwright.config.ts` sets no `maxDiffPixelRatio`, so
`toHaveScreenshot` allows zero differing pixels. The legal-search suite carried a
project-level `0.06` — ~86,000 pixels on a 1600x900 full-page shot — and stayed
green across a ~260px mislaid layout region for 3.5 months (#605/#611). Do not
reintroduce a default; scope slack to one call with a written justification.

**Baselines are generated in CI.** Add the `visual-baseline-refresh` label to the
PR and push. `admin-visual-baseline-refresh` regenerates on `ubuntu-latest` — the
same runner that verifies — and appends an entry to
`platform-control/admin/e2e/visual.spec.ts-snapshots/PROVENANCE.md`. Generation
and verification must share an environment: font rasterisation differs between
machines and zero tolerance does not forgive it.

**Every baseline change needs a recorded reason.**
`scripts/check_visual_baseline_provenance.py` guards both snapshot directories and
fails CI and pre-commit if a `*.png` changes without a matching `PROVENANCE.md`
entry naming it. It also rejects the refresh job's own placeholder `Reason:`, so a
machine-generated image cannot go green until a human says why it is correct.
"The tests were red" is not a reason — re-blessing to restore green is precisely
how three legal-search baselines came to certify live bugs.

**Pixels are the wrong tool for geometry.** A clipped column or an overflowing
table is small in pixel terms and fatal in use. Assert those with bounding-box
checks (`run-detail-sections.spec.ts`, `operator-usability.spec.ts`), which state
the invariant outright, and reserve screenshots for styling.

---

## What NOT to Overbuild Early

- Do not build comprehensive CRUD tests for every entity — focus on state transitions and boundaries
- Do not test database query performance — correctness first
- Do not build broad UI automation for the React-admin app early — prefer API and service tests; add targeted Playwright only for critical operator flows when they stabilize. (Those flows have stabilized: the suite described above exists, and #686 documents why running it is not optional.)
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
