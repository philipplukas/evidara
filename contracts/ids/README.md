# Evidara ID Conventions

## Overview

All contract-level entities in Evidara use string identifiers with stable family prefixes.
IDs are designed to be:

- globally unique within their family
- easy to recognize in logs and payloads
- safe to carry across API, event, and storage boundaries

## ID Families

| ID | Owner | Format | Example |
|----|-------|--------|---------|
| `tenant_id` | platform-control | `tenant_{slug}` | `tenant_public` |
| `corpus_id` | platform-control | `corpus_{slug}` | `corpus_public_ch_federal_law` |
| `source_id` | platform-control | `src_{ulid}` | `src_01jq79xv3wdd6yr8q5bn0m3zfk` |
| `source_version_id` | platform-control | `sv_{ulid}` | `sv_01jq79zcslf4m3m4gm3t5s59xq` |
| `run_id` | platform-control | `run_{ulid}` | `run_01jq7a3s9b7j4dndd9sgv6pb9d` |
| `source_snapshot_id` | platform-control | `snap_{ulid}` | `snap_01jq7a7n3nbzj6sk7v95p9frz1` |
| `artifact_id` | platform-control | `art_{ulid}` | `art_01jq7af3f8qqc46zc6xvkf9y4x` |
| `bundle_manifest_id` | platform-control | `abm_{ulid}` | `abm_01jq7ab8x4nm7m3qz3b8e9q2fk` |
| `reference_snapshot_set_ref` | platform-control | `rss_{ulid}` | `rss_01jq7cm7b9qg4w7g6b0k9g4xj2` |
| `document_id` | document-intelligence | `doc_{ulid}` | `doc_01jq7bdptzqv3xs0c41xpw1ybg` |
| `section_id` | document-intelligence | `sec_{ulid}` | `sec_01jq7bprm7p1ef4rwr7s2j1bt3` |
| `citation_id` | document-intelligence | `cit_{ulid}` | `cit_01jq7bwpt6mjjd7c9wqgt28v87` |
| `insight_id` | document-intelligence | `ins_{ulid}` | `ins_01jq7c1ny0ffv8qdr1xwbejqb6` |
| `processing_manifest_id` | document-intelligence | `pm_{ulid}` | `pm_01jq7bhgy7g0pkj4f1d03f8f8c` |
| `projection_manifest_id` | legal-search | `prm_{ulid}` | `prm_01jq7cq8m4qydv1w0fdy6jnbn5` |
| `event_id` | event producer | `evt_{ulid}` | `evt_01jq7c61be9zmhz58mmp3jx0b2` |
| `jurisdiction_id` | platform-control | `jur_{slug}` | `jur_ch_federal` |
| `authority_id` | platform-control | `auth_{slug}` | `auth_fedlex` |
| `correction_id` | platform-control | `cor_{ulid}` | `cor_01jqs7m4dxn5e6vh7q2bzcjt8r` |
| `operator_id` | platform-control | `op_{ulid}` | `op_01jqs7p1bcvz2tw5kxh9mq80fg` |

## Format Rules

- Prefixes are lowercase and indicate the entity family.
- ULID-backed IDs should use lowercase Crockford base32 for consistency.
- Slug-backed IDs should use lowercase letters, digits, and underscores only.
- IDs are opaque to consumers. Prefix recognition is fine; parsing business meaning out of the suffix is not.

## Ownership

- The component that creates an entity assigns its ID.
- IDs are carried across boundaries as references but are never reassigned.
- `document_id` is stable for the logical document within its corpus.
- `processing_manifest_id` is immutable for one DI processing result.
- `document_revision` is not an ID; it is a monotonic revision number owned by document-intelligence.

## Reserved Values

- `tenant_public` is the reserved non-null tenant ID for globally shared public data.

## Field Naming Best Practices

- Use `*_id` for stable identity fields.
- Prefer `*_ref` for typed indirection to a storage object, dataset surface, or manifest.
- Record timestamps as `*_at` in ISO 8601 UTC.
- Reserve `*_version` for major contract versions or pipeline/projection versions.
- Represent lifecycle or workflow state with `*_status`.
- Use `snake_case` for field names and `dot.separated` `event_type` names.

### Exception: `reference_snapshot_set_ref`

`reference_snapshot_set_ref` is an exception to the `*_ref` naming convention. Despite the `_ref` suffix, it is a scalar ID field (following the `rss_{ulid}` pattern), not a typed indirection object. This name was chosen to emphasize that it references an external reference-data snapshot set owned by platform-control, rather than being a direct identity field within the consuming schema. The `_ref` suffix here indicates cross-boundary reference semantics, not object structure.

## Uniqueness And Stability

- IDs are unique within their family.
- IDs are never reused.
- Human-editable names and labels must not be used as cross-component identifiers.

## Evolution Rules

- New ID families should be added here before they appear in contracts.
- Changing the format or meaning of an existing ID family is breaking and requires an ADR.
