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
- Object payload indirection should use typed refs such as `storage_object_ref`, `dataset_ref`, and `manifest_ref`.
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
