# Wizard Discovery and Extraction Contracts

Defines logical contract shapes for the wizard flow used by platform-control for hierarchical discovery and extraction.

> **ADR-0031.** Argilla is deleted; review tasks live in the `review_tasks` table and are worked in `platform-control/admin`. The confidence-band routing policy is retained (`docs/runbooks/extraction-review-routing.md`).

This document is the contract companion for:

- `docs/architecture/temporal-argilla-wizard-architecture.md`
- `contracts/api/platform-control.openapi.yaml` (API transport surface)

## Versioning rules

- Every entity includes `contractVersion`.
- Breaking changes increment major version (`v1` -> `v2`).
- Additive non-breaking fields increment minor version (`v1.1`).
- Deprecated fields must be maintained for at least one release cycle.
- Persisted records keep original `contractVersion`; no in-place mutation.

## SourceNode

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `uuid` | yes | Immutable identity |
| `parentId` | `uuid` | no | Parent in hierarchy tree |
| `sourceId` | `uuid` | yes | Control-plane source reference |
| `url` | `string` | yes | Canonicalized URL |
| `nodeType` | `enum` | yes | `domain|section|listing|document` |
| `crawlPolicy` | `object` | yes | Depth/include/exclude/rate controls |
| `effectiveFrom` | `timestamp` | yes | Policy applicability start |
| `version` | `integer` | yes | Node revision counter |
| `contractVersion` | `string` | yes | Contract semantic version |

## ExtractionSchema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `uuid` | yes | Immutable identity |
| `name` | `string` | yes | Stable schema name |
| `version` | `string` | yes | Semantic version |
| `fields` | `array` | yes | Field definitions + types |
| `normalizationRules` | `object` | yes | Canonicalization/cleanup rules |
| `requiredFieldSet` | `array` | yes | Required field names |
| `contractVersion` | `string` | yes | Contract semantic version |

## ExtractionRecord

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `uuid` | yes | Immutable identity |
| `runId` | `uuid` | yes | Run scope |
| `sourceNodeId` | `uuid` | yes | Origin hierarchy node |
| `schemaId` | `uuid` | yes | Schema reference |
| `schemaVersion` | `string` | yes | Schema version pin |
| `rawArtifactUri` | `string` | yes | Raw capture reference |
| `structuredPayload` | `object` | yes | Extracted typed payload |
| `fieldConfidence` | `object` | yes | Per-field confidence map |
| `recordConfidence` | `float` | yes | Aggregate confidence score |
| `status` | `enum` | yes | `accepted|needs_review|rejected` |
| `contractVersion` | `string` | yes | Contract semantic version |

## Provenance

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `uuid` | yes | Immutable identity |
| `recordId` | `uuid` | yes | ExtractionRecord reference |
| `sourceUrl` | `string` | yes | Fetched URL |
| `retrievedAt` | `timestamp` | yes | Fetch timestamp |
| `workerVersion` | `string` | yes | Worker build/version |
| `modelVersion` | `string` | no | LLM/model identifier if used |
| `promptHash` | `string` | no | Prompt digest if used |
| `parserSignature` | `string` | yes | Deterministic parser signature |
| `attempt` | `integer` | yes | Retry attempt number |
| `contractVersion` | `string` | yes | Contract semantic version |

## ReviewTask

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `uuid` | yes | Internal review task id |
| `runId` | `uuid` | yes | Run scope |
| `recordId` | `uuid` | yes | ExtractionRecord reference |
| `externalId` | `string` | yes | Producer-supplied dedupe key (unique). Was `argillaDatasetId` / `argillaRecordId` before ADR-0031 |
| `disputedFields` | `array` | yes | Fields needing review |
| `suggestedValues` | `object` | yes | AI-proposed values |
| `reviewDecision` | `enum` | no | `accept|edit|reject` when complete |
| `reviewRationale` | `string` | no | Reviewer explanation |
| `reviewedBy` | `string` | no | Reviewer identifier |
| `reviewedAt` | `timestamp` | no | Completion time |
| `contractVersion` | `string` | yes | Contract semantic version |

## RunLedger

| Field | Type | Required | Notes |
|---|---|---|---|
| `runId` | `uuid` | yes | Internal run identifier |
| `workflowId` | `string` | yes | Temporal workflow id |
| `stateTransitions` | `array` | yes | Enter/exit timing per state |
| `retryCounters` | `object` | yes | Retry counts by activity |
| `errorSummary` | `object` | yes | Aggregated terminal and non-terminal failures |
| `slaMarkers` | `object` | yes | SLO timing checkpoints |
| `publishedVersion` | `string` | no | Published output version pointer |
| `contractVersion` | `string` | yes | Contract semantic version |
