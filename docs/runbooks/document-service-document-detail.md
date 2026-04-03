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
4. **Validate environment config** — BFF must point at the correct Document Service base URL and credentials (when enabled).

## Symptom: Slow document detail (high latency)

1. **Payload size** — Lean vs full Docling JSON; prefer `/lean` for UI paths.
2. **Cold Databricks SQL warehouse** — If Phase 1 uses SQL REST, warehouse startup dominates first queries.
3. **OpenSearch** — Separate metadata latency from body latency using BFF structured logs.

## Correlation IDs

- Forward **`X-Correlation-Id`** from the BFF to the Document Service on every request.
- Search logs by correlation ID across **frontend → BFF → Document Service** (and Databricks query IDs when available).

## Escalation data to collect

- Timestamp, environment, `document_id`, `document_revision`, correlation ID, HTTP status from Document Service, redacted request path.
- Whether search hits return the same `document_id` (isolates OpenSearch vs body path).

## Related docs

- [NFRs & SLOs](../architecture/nfrs-and-slos.md)
- [Security & Tenancy](../architecture/security-and-tenancy.md)
- [Data Lifecycle](../architecture/data-lifecycle.md)
