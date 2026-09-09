# Contracts

`contracts/` is the highest-authority interface layer in Evidara. If prose and a contract file disagree, the contract file wins.

## Directory Layout

```text
contracts/
  api/       # OpenAPI specs for synchronous APIs
  common/    # Reusable JSON Schema building blocks
  events/    # JSON Schemas for async event envelopes and payloads
  examples/  # Example payloads validated against schemas
  ids/       # ID families and field naming guidance
  schemas/   # Shared domain and manifest schemas
```

### Hand-authored vs generated

| File | Authored | Change it by |
|---|---|---|
| `api/legal-search.openapi.yaml` | By hand, before the code (ADR-0008) | Editing the file; clients regenerate from it via Orval (ADR-0007) |
| `api/document-intelligence*.openapi.yaml` | By hand | Editing the file |
| **`api/platform-control.openapi.yaml`** | **Generated from the FastAPI app** (ADR-0034) | Changing `platform-control/src/platform_control/` and running `scripts/generate_platform_control_contract.py` — **never** by editing the file |

The platform-control spec is generated because hand-maintaining it drifted it to 4 of
11 acquisition providers and caused two production bugs (#614, #616 — see #618).
`scripts/check-platform-control.sh` fails the build when it and the app disagree.
It is no less a contract for being generated; it is more of one, because it is the
only file here that cannot be wrong about its service.

## Design Rules

- Contracts define boundaries, not internal implementation classes.
- APIs are for control/query interactions.
- Events are for pipeline progression and asynchronous status reporting.
- Manifests and typed refs are preferred over giant payload events.
- Published dataset refs must point to stable logical surfaces, not ad hoc internal table names.
- All cross-component payloads must carry enough provenance to trace source, version, run, and corpus ownership.

## Standards And Platform Capabilities

- JSON payloads use JSON Schema Draft 2020-12.
- Synchronous APIs use OpenAPI 3.1.
- Async events use a CloudEvents-aligned envelope shape, even when the business payload remains Evidara-specific.
- Object payload indirection should use typed refs such as `storage_object_ref`, `dataset_ref`, and `manifest_ref` defined in `contracts/common/storage-object-ref.schema.json`, `contracts/common/dataset-ref.schema.json`, and `contracts/common/manifest-ref.schema.json`.
- Prefer platform-native lineage and lifecycle features where they fit:
  - Databricks / Unity Catalog for table and job lineage inside document-intelligence
  - OpenSearch versioned indices and aliases for search cutovers and rebuilds
- Keep contracts focused on domain-specific identities, lifecycle transitions, and published-surface refs rather than duplicating every internal operational detail into payloads.

## Naming Conventions

- Field names use `snake_case`.
- Event names use dotted `snake_case`, for example `artifact_bundle.available`.
- Infrastructure topic names use kebab-case, for example `artifact-bundle-available`.
- Schema titles use `PascalCase`.
- Contract files are singular by concept where possible, for example `document.schema.json`.

## Versioning Conventions

- Event names are stable and versionless.
- Events carry `event_version`.
- Additive optional fields are allowed within a version.
- Removing a field, tightening a constraint, or changing semantics is breaking and requires a new version plus an ADR.
- Manifest contracts carry `manifest_version`.
- Published dataset refs carry `surface_version`.

## MVP Contract Lock File

`contracts/manifest.yaml` is the machine-checked lock file for the current
MVP ingest-to-search product flow:

- source create -> version create/approve -> run -> DI outputs -> searchable detail
- locked API spec files and versions for platform-control, document-intelligence, and legal-search
- locked event schemas and `event_version` values for core pipeline events

CI validates this file via `scripts/check_contract_manifest.py`.

### Changeset Guard

CI enforces a declaration rule via `scripts/check_contract_version_bump.py`:

- If any file under `contracts/api/` or `contracts/events/` changes, the PR must add a
  changeset under [`contracts/changes/`](changes/README.md) — write it with
  `python3 scripts/bump_contract_version.py --minor --summary "..."`.
- Every changeset in the tree is validated on every run of the gate, not only the ones a PR touched.
- The top-level `version` here is **not** hand-edited. `scripts/release_contract_version.py`
  computes it from the pending changesets and is its only writer.

Until 2026-09-09 the rule was instead "bump the top-level `version`", which made every contract PR
contend for one line and is what #913 named as a blocker to parallel work. See
[`contracts/changes/README.md`](changes/README.md) for the two measured failure modes.

The released version is still the signal that locked cross-service contract surfaces changed; it now
moves per release rather than per PR.

## Field Suffix Conventions

- `*_id`: stable identity
- `*_ref`: typed indirection
- `*_at`: timestamp
- `*_version`: contract, processing, or projection version
- `*_status`: lifecycle or workflow state

## Example Payload Guidance

- Every important schema should have at least one example under `contracts/examples/`.
- Examples must use realistic values, not placeholders like `foo` or `123`.
- Examples are part of the contract surface and should be updated in the same PR as the schema.

## Small-Team Bias

- Prefer a few strong contracts over many narrow ones.
- Keep override mechanisms explicit and rare.
- Use one real boundary pattern from day one rather than temporary shortcuts that will need to be unwound later.
