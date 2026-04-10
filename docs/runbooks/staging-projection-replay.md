# Staging — projection replay (legal-search BFF)

Use this to **refresh OpenSearch rows** after BFF projection logic or Document Service lean payloads change, without re-running full DI.

**Prerequisites**

- **Audience-scoped ID token** for the staging **legal-search API** Cloud Run URL (same pattern as e2e: `gcloud auth print-identity-token --impersonate-service-account=… --audiences=https://…legal-search-api-staging….run.app`), or deployment-specific API key if configured.
- A contract-shaped **`document.processed`** JSON body (see [`scripts/fixtures/document-processed.example.json`](../../scripts/fixtures/document-processed.example.json)). Use a **new** `event_id` each replay.

**Steps**

1. Set `LS_URL` to the staging legal-search API base (no trailing slash), e.g. from [`infra/env/staging/runtime.gcp.tfvars.example`](../../infra/env/staging/runtime.gcp.tfvars.example).
2. Mint `TOKEN` (Bearer) with an audience matching `LS_URL`.
3. POST:

```bash
curl -sS -X POST "${LS_URL}/v1/projections/events/document-processed" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

4. Confirm `{"status":"applied"}` (or understand `ignored_duplicate` / stale rules in [metadata quality plan — section 6.4](metadata-quality-plan-status.md)).
5. `GET ${LS_URL}/v1/search?q=…` and document detail for the `document_id` — compare to [section 3.5](metadata-quality-plan-status.md) acceptance.

**TAR-89:** Staging **cannot** be signed off (template **3.5.3**) until search/detail meet section 3.5 for the agreed IDs — replay alone is insufficient if lean still lacks title/type hints.
