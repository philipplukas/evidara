# Argilla Review Routing and Sync

Owner: Platform team  
Last reviewed: 2026-04-07  
Last verified: 2026-04-07 (docs metadata and CI runbook lint)  
Applies to: dev, staging (platform-control API + Argilla integration)

## Purpose

Define how platform-control routes uncertain extraction results to Argilla and ingests reviewer outcomes back into control-plane records.

Current API ingress path:

- `POST /v1/reviews/tasks` — create `ReviewTask`, optional outbound enqueue to Argilla when `PLATFORM_CONTROL_ARGILLA_*` is set
- `POST /v1/reviews/sync-from-argilla`
- `GET /v1/reviews/tasks/{task_id}`

## Preconditions

- `WizardRunWorkflow` has completed extraction and validation stages.
- `ExtractionRecord` rows include per-field confidence.
- Argilla workspace, dataset, and API credentials are configured.

## Routing policy

Threshold defaults:

- `highThreshold = 0.90`
- `lowThreshold = 0.70`

Route outcomes:

- `recordConfidence >= 0.90`: auto-accept; include 5% random audit sample in Argilla.
- `0.70 <= recordConfidence < 0.90`: enqueue sampled review (minimum 20%).
- `recordConfidence < 0.70`: mandatory Argilla review.
- Any extractor conflict (`conflict=true`): mandatory Argilla review, independent of confidence.

## Argilla task payload

The review enqueue payload should map 1:1 with internal `ReviewTask` identity.

```json
{
  "external_id": "3b2e67d1-95f4-4a44-b4e7-6c0f8434f0b4",
  "metadata": {
    "runId": "9b8e7cfa-1f44-4bd8-8d0f-9c9e7278ad2f",
    "recordId": "5233d1d8-0e82-4ca1-8f96-4312adf9d7d8",
    "sourceNodeId": "f8c18d46-e773-47f8-9b9d-cd4b7ec6af1a",
    "schemaVersion": "1.0.0",
    "recordConfidence": 0.66
  },
  "fields": {
    "source_excerpt": "string",
    "structured_candidate": {
      "title": "string",
      "effective_date": "2026-04-01"
    },
    "disputed_fields": ["effective_date"]
  },
  "suggestions": [
    {
      "field": "effective_date",
      "value": "2026-04-01",
      "confidence": 0.66
    }
  ],
  "guidelines": "Verify date format and legal act effective date semantics."
}
```

## Review completion ingestion flow

1. Export completed Argilla annotations via webhook or polling.
2. Verify source authenticity and payload schema.
3. Resolve `external_id` to internal `ReviewTask.id`.
4. Persist `reviewDecision`, `reviewRationale`, `reviewedBy`, and `reviewedAt`.
5. Apply decision to `ExtractionRecord`:
   - `accept` -> set status `accepted`.
   - `edit` -> write corrected payload, set status `accepted`.
   - `reject` -> set status `rejected` and keep conflict marker.
6. Emit correction signal for prompt/rule/model iteration.

## Idempotency and dedupe

- Use `external_id` + `annotation_updated_at` as dedupe key.
- Ignore older updates when a newer review already exists.
- Record ingestion attempt metadata to `RunLedger.errorSummary` for diagnostics.

## Failure handling

- Validation failure: send payload to review-sync DLQ and alert on-call.
- Missing `external_id` mapping: mark as orphaned review and queue manual reconciliation.
- Write conflict: retry with optimistic concurrency; if exhausted, DLQ.

## Operational checks

- Review backlog by priority and age.
- Orphaned review count.
- Review-sync DLQ depth.
- End-to-end lag from `ReviewTask` creation to status application.
