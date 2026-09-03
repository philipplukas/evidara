# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for acquisition, governance, approval, and scope metadata.

## Current state

Platform-control now has a running FastAPI service with persisted entities and migration-backed schemas for source lifecycle, runs, webhook receipts, raw artifacts, bundle manifests, and DI status/lifecycle event consumption. Core API endpoints are implemented for sources, versions, runs, Firecrawl callbacks, and DI event ingest (`document.processing_status.updated`, `document.processed`, `document.withdrawn`) with run-scoped read surfaces.

For the current slice, scope fields such as `tenant_id`, `corpus_id`, and `scope_type` are frozen through source-version acquisition config and copied into bundle/event provenance. Run creation accepts explicit `scope` and `replay` metadata for partial reruns and backfills. Acquisition webhooks now persist a `replay_checkpoint` object on the run (Firecrawl-driven fields such as `last_firecrawl_event_type` and `pages_ingested`), and child runs created with `replay.parent_run_id` inherit the parent checkpoint when present so operators can reason about resume frontiers without direct database surgery. First-class corpus CRUD is still follow-on work.

Wizard API v1 foundation is available with persisted project/run/review/ledger entities plus orchestration abstraction wiring (`in_memory` default, `temporal` backend). With `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND=temporal`, the API starts a `WizardRunWorkflow` execution (workflow id `wizard-run-{wizard_run_id}`) and sends approve/reject signals; run `platform-control-temporal-worker` against the same `PLATFORM_CONTROL_TEMPORAL_*` settings so workflows make progress. Temporal workers register `WizardRunWorkflow`, `ScopeShardWorkflow`, and `ReviewDrainWorkflow`. After operator approve, the parent runs a pilot scope-shard child and a review-drain child (stubs today; real activities and multi-shard fan-out are follow-on). Pilot-completion-driven `HUMAN_GATE_APPROVAL` persistence remains follow-on; see ADR-0021 and `docs/architecture/temporal-argilla-wizard-architecture.md`.

Review loop: `POST /v1/reviews/tasks` persists a `ReviewTask` — and persisting it *is* the enqueue, since the queue is the `review_tasks` table that `platform-control/admin` reads. What gets routed there is decided by the confidence-band policy (`>= 0.90` auto-accept with a 5% audit sample; `0.70–0.90` sampled at `>= 20%`; `< 0.70` mandatory; any extractor conflict mandatory). An operator closes a task with `POST /v1/reviews/tasks/{task_id}/decision`; a second verdict on an already-decided task is a `409`. The Argilla enqueue and `POST /v1/reviews/sync-from-argilla` were removed in ADR-0031 — see `docs/runbooks/extraction-review-routing.md`.

See [Platform Control Implementation Plan](platform-control-implementation-plan.md) for the planned repo structure, worker layout, and phased delivery approach.

## Source of truth

- Postgres (Cloud SQL) for sources, versions, runs, approvals, and reference data
- GCS for raw artifacts and immutable artifact bundle manifest objects
- `contracts/api/platform-control.openapi.yaml` for API definition
- `contracts/schemas/artifact-bundle-manifest.schema.json` for immutable DI handoff manifests

## Responsibilities

### Minimal v1

- Scope metadata (`tenant_id`, `corpus_id`, `scope_type`) frozen for the run and handoff path
- Jurisdictions and authorities (reference data)
- Source registry
- Source versions as frozen governed acquisition config
- Run records and acquisition checkpoints
- Source snapshots, artifact registration, and bundle manifests

Bundle manifests should be published as immutable JSON objects. If platform-control needs to query them operationally, it should mirror searchable fields into its own query surfaces rather than relying on path parsing conventions.

### Boundary

- **Does own:** source lifecycle, scope governance, reference data, runs, approvals, connector execution, provenance registration
- **Does NOT own:** canonical document truth, search projections, parsing, canonical resolution

## Minimal next tasks

- [x] Define Postgres entities for sources, versions, runs, provider jobs, artifacts, and DI event tracking
- [x] Define OpenAPI spec (`contracts/api/platform-control.openapi.yaml`)
- [x] Define `ArtifactBundleManifest` schema
- [x] Create the initial `platform-control/` API scaffold
- [x] Create the connector-worker scaffold under `platform-control/`
- [x] Define run lifecycle and replay modes
  Runs expose `replay_checkpoint` on `GET /v1/runs/{run_id}` (see OpenAPI `Run`). Checkpoints advance on Firecrawl webhook progress; Temporal scope-shard starts accept an optional `resume_token` for future activity-backed resume wiring.
- [x] Define approval states and transitions
- [x] Define reference snapshot export mechanics for DI
- [x] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)

Replay/checkpoint constraint: checkpoints are JSON metadata on `runs`, not a separate table. Provider-specific keys may appear under `replay_checkpoint`; treat unknown keys as opaque operational hints until normalized in a later schema pass.

## Minimal v1 Outcome

A user can:

1. Create a source and freeze scope metadata for the run path
2. Create and approve a source version
3. Trigger a run with replay/backfill scope
4. Register a source snapshot and one or more artifacts
5. Publish an immutable bundle manifest and emit `artifact_bundle.available`

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Reference-data editing UI |
| Next | Drift and repair workflows |
| Later | AI-generated draft source versions |
| Later | More granular source family support |

## Discovery drift outputs (non-authoritative)

Acquisition discovery may observe metadata that does not cleanly map to canonical taxonomy keys. These observations are operational evidence, not contract changes.

- Discovery outputs should be recorded as run-scoped drift artifacts (for example, candidate alias/mapping patches) linked to the run record.
- Drift artifacts may include proposed values for jurisdiction aliases, source-family mapping candidates, language-pair candidates, and court/authority label normalization.
- Platform-control must not mutate country overlay YAML/config at runtime.
- Accepted mapping changes are applied through reviewed docs/config updates, then used by subsequent runs.

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Cloud SQL (Postgres) | Control-plane metadata |
| GCS | Raw artifacts and bundle manifests |
| Pub/Sub | Event emission and status consumption |
| Cloud Run | Runtime |

## Platform Capabilities We Reuse

- Pub/Sub for event transport
- CloudEvents-aligned event metadata through the shared contract envelope
- GCS object immutability patterns for durable raw artifacts and manifest storage

Lineage and document semantics that cross boundaries still remain Evidara-owned contracts.

## Key Contracts

- **Produces:** `artifact_bundle.available`
- **Consumes:** `document.processing_status.updated`, `document.processed`, `document.withdrawn`
- **API:** `contracts/api/platform-control.openapi.yaml` — **generated** from this app ([ADR-0034](../adr/0034-generated-platform-control-contract.md)); do not hand-edit
- **Schemas:** `ArtifactBundleManifest`

## Authentication

When any of `PLATFORM_CONTROL_API_KEY`, `PLATFORM_CONTROL_OPERATOR_API_KEY`, or
`PLATFORM_CONTROL_SERVICE_API_KEY` is set, matching routes require `X-API-Key`.
Unset keys keep local development open. Legacy single-key mode is
`PLATFORM_CONTROL_API_KEY` only; scoped operator vs service keys are documented in
[ADR-0020](../adr/adr-0020-api-authentication.md).

## Developer workflow

- Service check: `bash scripts/check-platform-control.sh` (ruff, pytest, and the OpenAPI contract drift gate)
- Regenerate the OpenAPI contract after changing routers or schemas:
  `cd platform-control && uv run python ../scripts/generate_platform_control_contract.py`
- Docs/contracts checks: `bash scripts/check_docs.sh`
- Legal-search checks (cross-component CI parity): `bash scripts/check-legal-search.sh`

Multi-country operator scaling references:

- `docs/components/five-country-content-rollout.md`
- `docs/runbooks/platform-control-multi-country-operator-playbook.md`
- `docs/architecture/temporal-argilla-wizard-architecture.md` (Argilla sections superseded by ADR-0031)
- `docs/runbooks/extraction-review-routing.md`

HITL (corrections, commentary overlays, canonical filters) rollout:

- `docs/runbooks/hitl-rollout.md` — sequenced rollout, replay/re-index, smoke, rollback for the M7–M10 HITL track.

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the full testing strategy.

Key tests:

- Unit tests for run and approval state transitions
- Contract tests for `ArtifactBundleManifest`
- Contract tests for `artifact_bundle.available`
- Contract tests for consumed `document.processing_status.updated` values, including invalid-status handling
- Smoke test for one source family lifecycle

## Capture guards

Two gates decide whether captured bytes may enter the artifact pipeline. They answer
different questions and neither subsumes the other, so a provider fetching a binary
manifestation needs the first before the second is even meaningful:

| Gate | Question | Catches | Blind to |
|---|---|---|---|
| `acquisition_core.artifact_guard.check_capture` | "are these the bytes I asked for?" | declared/expected content-type mismatch, missing format magic, HTML where a binary was expected, a size floor (#716) | a well-formed page whose text is not law |
| `acquisition_core.content_gate.assess_legal_text_density` | "does this text look like law?" | a JavaScript or navigation shell served as a statute (#631) | binaries — it abstains on anything outside HTML/XML, deliberately |

Neither judges the **text inside a PDF**; that needs extraction and belongs to
document-intelligence's quarantine gate (ADR-0047). `artifact_guard` must not grow a
marker check of its own: the vocabulary and threshold live in `content_gate` and are
pinned across both components by
`document-intelligence/tests/test_quarantine.py::MarkerVocabularyDriftTests`.

**Which provider calls which is a decision, not a default.** A gate configured for the
wrong modality or the wrong language is worse than none, because it refuses honest
captures while looking like protection — `eur_lex_sparql` defaults to English and
`legifrance` is French, both outside `content_gate`'s DE/IT marker vocabulary, so both
are deliberately ungated. The matrix, including those reasons, lives in
`platform-control/tests/unit/test_capture_guard_coverage.py` and is **asserted**: a
provider registered without a recorded decision, or whose capture path stops matching
the one it has, fails that test. Read it before adding a provider.

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes silently | Artifact count and content-type drift checks |
| Run state becomes inconsistent | Unit tests for valid and invalid transitions |
| Bundle manifests drift from DI expectations | Schema validation and example payload tests |
| Scope metadata changes accidentally | Source-version governance, manifest provenance, and audit trail |
| A capture gate is wired to a provider it does not fit, or a new provider is added with neither | `tests/unit/test_capture_guard_coverage.py` — the matrix is an assertion over the live registry, not a comment |
