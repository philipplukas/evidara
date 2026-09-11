# Runbook: Document Service & document detail

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging, prod

## Scope

User-facing **document detail** combines OpenSearch-backed metadata from the **legal-search BFF** with the document body from the **Document Service** (document-intelligence read boundary). See ADR-0010 and `contracts/api/document-intelligence.openapi.yaml`.

## Symptom: 404 or empty body on detail page

1. **Confirm identity of the document** — `document_id` and optional `document_revision` match a published row.
2. **Check BFF logs** — Look for upstream errors calling the Document Service base URL.
3. **Verify `document.processed` was emitted** — Search projection and body reads both depend on publication signals and published Delta surfaces.
4. **Validate environment config** — BFF must point at the correct Document Service base URL and bearer credential pair (`DOCUMENT_INTELLIGENCE_BASE_URL`, `DOCUMENT_INTELLIGENCE_API_KEY` / `DOCUMENT_SERVICE_BEARER_TOKEN`).

## Symptom: `503` from the Document Service ("Published sections are temporarily unavailable")

This is a **deliberate refusal**, not a crash (#972). The store answers `503` when the
published-sections read *failed* — a schema mismatch, a filter against a column the table does not
have, an unreadable surface, a credential problem. It exists because the alternative is worse: until
this landed, every one of those returned `[]`, which is exactly what a document with genuinely zero
sections returns, so a broken read rendered as *"this document has no sections"*.

A document that truly has no sections still answers `200` without a `sections` array, and a sections
surface that has never been written is a genuine zero, not a refusal.

1. **Read the log line** — `published_sections_unavailable` carries the surface `uri` and the
   underlying error; `published_sections_unavailable_refusal` marks the HTTP answer.
2. **Check the sections surface schema** — the most common cause is a `published_sections` table
   missing a column `get_full` filters on (`document_id`, `document_revision`,
   `processing_manifest_id`). Compare against `PUBLISHED_SECTIONS`.
3. **Check credentials and the surface root** — `DI_SURFACES_ROOT_URI` and the `DI_S3_*` pair must
   reach the same object store the consumer wrote to.
4. **Do not "fix" it by widening the catch.** Serving the document as section-less is the failure
   mode this refusal replaced.

## Symptom: Slow document detail (high latency)

1. **Payload size** — Lean vs full Docling JSON; prefer `/lean` for UI paths.
2. **Cold published-surface read path** — Delta-backed reads can be slower on the first request if the service is cold or the backing store path is newly mounted.
3. **OpenSearch** — Separate metadata latency from body latency using BFF structured logs.

## Runtime wiring checklist

1. **Document Service deployment** — Confirm `document-intelligence-document-service-{env}` is deployed and healthy.
2. **Published surface root** — Check `DI_SURFACES_ROOT_URI` points at the environment's `.../published` GCS root.
3. **BFF base URL** — Check `legal-search-api` is configured with the matching `DOCUMENT_INTELLIGENCE_BASE_URL`.
4. **Bearer pair** — If bearer protection is enabled, confirm the BFF `DOCUMENT_INTELLIGENCE_API_KEY` matches the service `DOCUMENT_SERVICE_BEARER_TOKEN`.
5. **Contract query** — Prefer `document_revision` when reading a specific revision; `processing_manifest_id` remains a compatibility path only.

## Correlation IDs

- Forward **`X-Correlation-Id`** from the BFF to the Document Service on every request.
- Search logs by correlation ID across **frontend → BFF → Document Service** (and Databricks query IDs when available).

## Escalation data to collect

- Timestamp, environment, `document_id`, `document_revision`, correlation ID, HTTP status from Document Service, redacted request path.
- Whether search hits return the same `document_id` (isolates OpenSearch vs body path).
- Whether the document exists in the published document Delta surface for the requested `document_revision`.

## Related docs

- [NFRs & SLOs](../architecture/nfrs-and-slos.md)
- [Security & Tenancy](../architecture/security-and-tenancy.md)
- [Data Lifecycle](../architecture/data-lifecycle.md)
