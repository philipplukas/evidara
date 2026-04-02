# ADR-0012: Layered Contract Governance

## Status

Accepted

## Date

2026-03-30

## Context

The BFF realignment (ADR-0011) surfaced an interface governance problem: the BFF mappers encode consumer assumptions about field presence, vocabulary values, and denormalized joins that are not captured in any explicit contract.

Three layers of truth exist in the system:

1. **Canonical producer output** — what document-intelligence writes to Delta
2. **Projection / OpenSearch documents** — what the indexing pipeline stores
3. **BFF ViewModels** — what the frontend receives

Only layers 1 and 3 had partial explicit contracts. Layer 2 was entirely implicit — embedded in adapter code and mapper lookup tables. This created a class of failures where upstream changes would not produce errors, but would cause silent UI quality degradation: generic badges, missing labels, empty counts, and broken breadcrumbs.

This is worse than a hard contract failure because production "works" and monitoring may not catch it. The breakage appears as quality erosion, not an outage.

## Decision

### Adopt a three-layer contract model

Each layer has a single job:

| Layer | Contract file | Owns | Does NOT own |
|---|---|---|---|
| **Canonical producer** | `contracts/schemas/document.schema.json` | Domain truth, normalized vocabularies, extraction artifacts | Counts, previews, UI concerns |
| **Projection** | `contracts/schemas/search-projection.schema.json` | Read-optimized shape, derived metrics, denormalized joins | Domain semantics, normalization rules |
| **BFF ViewModel** | `contracts/api/legal-search.openapi.yaml` | Presentation composition, labels, colors, actions | Domain truth, derivation logic |

The governing principle: **normalize upstream, denormalize in projection, present in BFF.**

### Formalize controlled vocabularies

Fields whose values control downstream behavior are governed by explicit vocabulary files in `contracts/vocabularies/`:

- `document-type.json` — normalized document type classification
- `jurisdiction.json` — ISO 3166-1 alpha-2 jurisdiction codes

**Rules:**

- Canonical output MUST emit only normalized vocabulary values.
- Aliases in vocabulary files are upstream normalization hints. They are NOT valid canonical values and consumers MUST NOT accept them as such.
- Adding a new vocabulary value requires coordinated rollout (vocabulary file + canonical producer + projection builder + BFF mapper).
- Removing a vocabulary value requires an ADR.

### Unknown vocabulary handling policy

> Unknown controlled vocabulary values are invalid at the producer contract level, but downstream consumers must degrade safely and emit telemetry rather than silently masking the issue.

Concretely:

| Boundary | Behavior |
|---|---|
| **Canonical producer** | Schema validation SHOULD reject unknown values in CI and controlled ingestion. Quarantine, don't crash the pipeline. |
| **Projection builder** | Pass through unknown values. Do not normalize at this layer. |
| **BFF mappers** | Accept with generic fallback display + structured warning (field, value, document_id). Never crash or blank the UI. |

### Separate stored projection from runtime enrichment

The projection schema (`search-projection.schema.json`) describes the **stored** OpenSearch document shape. Runtime fields attached at query time are NOT part of this schema:

- `snippet` — OpenSearch `highlight` API, generated per query
- `relevance_score` — OpenSearch `_score`, computed per query

### Field ownership and provenance

Every field in the projection schema has documented ownership in `search-projection.provenance.md`:

- **Owner** — which system produces the field
- **Source** — where the value comes from
- **Required/optional** — contract obligation
- **Default** — value when source is unavailable
- **Failure behavior** — what happens in the UI when the field is missing

### Nullability policy

Consistent across all layers:

- **Required integer fields** (counts): always present, default `0`. Never null or omitted.
- **Required string fields**: always present. Never null.
- **Optional fields**: omitted when unavailable. Never `null`. This avoids three-state logic (`present` / `empty` / `null`) in consumer code.
- Aligns with ADR-0011 conventions.

## Change Compatibility Rules

| Change | Layer | Breaking? |
|---|---|---|
| Add optional canonical field | Canonical | No |
| Add new vocabulary value | Canonical | Potentially — requires coordinated rollout |
| Remove vocabulary value | Canonical | **Yes** — requires ADR |
| Rename field | Any | **Yes** |
| Change count semantics | Projection | **Yes** |
| Add new derived field to projection | Projection | No |
| Change badge/action behavior in BFF | BFF | Consumer-visible, but not a contract break |
| Change required field to optional | Any | **Yes** |

## Consequences

- **Contract files** govern the coupling between layers. Changes to vocabulary files or schemas require review.
- **Mapper lookup tables** in the BFF are loaded from or validated against vocabulary files, not maintained as independent copies.
- **Observable fallbacks** replace silent degradation. Unknown values produce structured telemetry, not just generic UI.
- **Projection schema** becomes a first-class artifact. The projection builder (once implemented) will validate its output against this schema.
- **`structural_path`** is a canonical field representing intrinsic document structure. It may evolve from a delimited string to a structured array representation in the future.
- **`content_docling`** is a canonical field representing a first-class extraction artifact (ADR-0010). Storage and indexing constraints should be reviewed if documents become large.

## Rationale

### Why not just expand the canonical schema?

Stuffing derived fields (counts, previews, denormalized joins) into the canonical schema creates two problems:

1. It pollutes the domain model with serving concerns.
2. It forces document-intelligence to own fields it doesn't naturally produce.

### Why not keep it implicit?

Silent degradation is worse than a hard failure in most cases. Implicit contracts create "institutionalized blindness" where the system works but quality erodes. Observable contracts make drift visible.

### Why not hard-fail on unknown vocabularies?

Hard-failing in the BFF would crash the UI for one bad document. The correct enforcement point is upstream (producer schema validation in CI and ingestion). The BFF's job is resilient presentation, not domain validation.
