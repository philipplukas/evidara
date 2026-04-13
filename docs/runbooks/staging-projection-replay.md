# Staging — projection replay (legal-search BFF)

Owner: Platform / legal-search  
Last reviewed: 2026-04-09  
Last verified: 2026-04-09  
Applies to: staging legal-search BFF, OpenSearch projections, TAR-89 replay workflow

Use this to **refresh OpenSearch rows** after BFF projection logic or Document Service lean payloads change, without re-running full DI.

## Prerequisites

- **Audience-scoped ID token** for the staging **legal-search API** Cloud Run URL (same pattern as e2e: `gcloud auth print-identity-token --impersonate-service-account=… --audiences=https://…legal-search-api-staging….run.app`), or deployment-specific API key if configured.
- A contract-shaped **`document.processed`** JSON body (see [`scripts/fixtures/document-processed.example.json`](../../scripts/fixtures/document-processed.example.json)). Use a **new** `event_id` each replay.
- The exact **Document Service origin** used by that BFF (`DOCUMENT_INTELLIGENCE_BASE_URL`) and whether the service path is **bearer-protected** or not. Record both in TAR-89 evidence so replay proves the intended upstream, not only the POST target.

## Steps

1. Set `LS_URL` to the staging legal-search API base (no trailing slash), e.g. from [`infra/env/staging/runtime.gcp.tfvars.example`](../../infra/env/staging/runtime.gcp.tfvars.example).
1. Mint `TOKEN` (Bearer) with an audience matching `LS_URL`.
1. Record the BFF's `DOCUMENT_INTELLIGENCE_BASE_URL` and the Document Service auth model for this environment before replaying. For Cloud Run, inspect the `legal-search-api` service env and confirm whether the paired Document Service expects the shared bearer secret path or an open/internal read path.
1. POST:

```bash
curl -sS -X POST "${LS_URL}/v1/projections/events/document-processed" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

1. Confirm `{"status":"applied"}` (or understand `ignored_duplicate` / stale rules in [metadata quality plan — section 6.4](metadata-quality-plan-status.md)).
1. `GET ${LS_URL}/v1/search?q=…` and document detail for the `document_id` — compare to [section 3.5](metadata-quality-plan-status.md) acceptance.
1. When posting TAR-89 sign-off, include `LS_URL`, the exact `DOCUMENT_INTELLIGENCE_BASE_URL`, and the Document Service auth model in the evidence note.

**TAR-89:** Staging **cannot** be signed off (template **3.5.3**) until search/detail meet section 3.5 for the agreed IDs — replay alone is insufficient if lean still lacks title/type hints.
