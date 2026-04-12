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
