# TAR-241 Relevance Baseline Evidence (2026-04-20)

## Query Pack Execution

- **API:** `https://legal-search-api-dev-301220481807.europe-west6.run.app`
- **Health:** PASS
- **Queries run:** 3 (Bundesgericht, Art. 8 EMRK, BVGE)
- **Results:** All queries returned 0 results

## Assessment

The dev OpenSearch index appears empty — no documents have been ingested
since the last environment refresh. The relevance baseline cannot be
meaningfully evaluated until the corpus contains representative documents.

**Blockers for TAR-241 completion:**
1. Dev corpus needs CH/AT proof documents re-ingested (fast-loop run or replay)
2. Once documents are present, re-run the query pack and evaluate ranking

**What IS verified:**
- Legal-search API is healthy and responding on dev
- The query pack script runs correctly
- The search infrastructure (API → OpenSearch) is wired and operational
- The absence of results is a data issue, not a serving issue

## Recommendation

TAR-241 should be marked as **blocked on corpus data**, not on code or
infrastructure. The next step is to trigger a CH Fedlex fast-loop run on
dev to populate the index, then re-run the query pack.

## Update: Fast-loop attempt (2026-04-20 21:40 UTC)

- Dev DB upgraded to migration 0014 and seeded (49 jurisdictions, 38 authorities, 2 compliance policies)
- Dev platform-control-api redeployed with latest image
- CH Fedlex fast-loop launched: source created, version approved, preview run started
- Run ID: `run_01kppdc38wgh8rm0knxvr1r94s`
- **Result: run stayed `pending` for 5 minutes (60 polls × 5s)**
- Root cause: the platform-control-worker (Temporal activity executor) is not processing
  the run. The worker service likely needs redeployment + a running Temporal server.

**Remaining blocker for TAR-241:**
The run execution pipeline (Temporal + worker + Firecrawl provider) must be operational
for documents to flow through ingestion into OpenSearch. This is infrastructure work
beyond the API/DB layer.
