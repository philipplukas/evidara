# Platform Control Testing

## Scope

Testing strategy for the platform-control component, which owns:

- tenants, corpora, and reference data
- sources and source versions
- runs and approvals
- snapshots, artifacts, and bundle manifests

## Minimal Tests for MVP

### Unit tests

- Run lifecycle: `pending` → `running` → `completed` / `failed`
- Approval workflow: `draft` → `pending_approval` → `approved` / `rejected`
- Invalid transitions are rejected
- Source version validation rejects incomplete acquisition config

### Contract tests

- `ArtifactBundleManifest` payloads conform to JSON Schema
- `artifact_bundle.available` payloads conform to event schema
- Required lineage fields are present: `tenant_id`, `corpus_id`, `source_id`, `source_version_id`, `run_id`, `source_snapshot_id`, `bundle_manifest_id`

### Workflow tests

- Create source → create version → approve version
- Approved source version → create run → snapshot/artifacts/bundle manifest recorded
- Failed acquisition run transitions correctly and does not emit `artifact_bundle.available`

### Smoke tests

- One source family end-to-end: register source → approve version → trigger run → verify bundle manifest is recorded
- Health check endpoint returns 200

## Drift Checks

| Check | What it catches |
|-------|----------------|
| Artifact count not unexpectedly zero | Source has stopped producing |
| Content type still expected | Source format changed |
| Empty output detection | Run completed but produced nothing |
| Bundle manifest schema mismatch | DI boundary drift |
