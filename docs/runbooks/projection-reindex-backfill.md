# Projection Reindex & Backfill Runbook

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging, prod

## Overview

This runbook documents how to safely perform reindex and backfill operations
on the legal-search projection index (OpenSearch). These operations are needed
when the index mapping changes, data corruption occurs, or after a major
schema migration.

## Prerequisites

- `gcloud` authenticated, `npx` available
- Access to the OpenSearch cluster
- Knowledge of which environment you're targeting

## Architecture

```text
┌──────────────────────┐    alias cutover    ┌──────────────────────┐
│  index-v1 (old)      │ ──────────────────> │  index-v2 (new)      │
│  ← read alias        │                    │  ← read alias        │
│  ← write alias       │                    │  ← write alias       │
└──────────────────────┘                    └──────────────────────┘
```

The cutover script creates a new versioned index, optionally reindexes data,
then atomically swaps the read/write aliases. Zero-downtime.

## Read/write alias invariant

Search reads the `documents-read` alias; projections write the
`documents-write` alias. **Both must resolve to the same physical index** —
otherwise a projected document lands in the write index but never surfaces in
search (the single most likely place a document "disappears").

Three producers keep this invariant, all consuming the same canonical mapping
in `legal-search/api/src/core/opensearch/documents-index.mapping.ts`:

- **`legal-search-api` startup** — `bootstrapDocumentsIndex` (see
  `core/opensearch/documents-bootstrap.ts`) idempotently creates the physical
  index with the canonical mapping and points both aliases at it if the read
  alias is absent. Non-destructive: if the read alias already resolves (e.g. a
  cutover manages it), startup does nothing. Disable with
  `OPENSEARCH_BOOTSTRAP_ON_STARTUP=false`.
- **`scripts/seed-from-opencaselaw.ts`** (`npm run seed:index`) — bootstraps the
  aliases before bulk-indexing the OpenCaseLaw fixtures.
- **`scripts/opensearch-alias-cutover.ts`** — versioned reindex/cutover, points
  both aliases at the new index.

## Procedure: Full Reindex

### Step 1: Dry Run

Always preview what will happen before making changes:

```bash
cd legal-search/api
npx tsx scripts/opensearch-alias-cutover.ts --reindex --dry-run
```

Expected output:

```
[DRY RUN] No changes will be made.
[1/4] Creating new projection index: evidara-documents-read-dev-20260403120000
[2/4] Reading current alias targets...
  read alias → [evidara-documents-read-dev-20260402...]
  write alias → [evidara-documents-read-dev-20260402...]
[3/4] Reindexing data: evidara-documents-read-dev-20260402... → evidara-documents-read-dev-20260403...
  [DRY RUN] Would reindex from evidara-documents-read-dev-20260402...
[4/4] Cutting over aliases...
  [DRY RUN] Would remove 1 read + 1 write targets...
```

### Step 2: Execute Reindex + Cutover

```bash
npx tsx scripts/opensearch-alias-cutover.ts --reindex
```

### Step 3: Verify

```bash
# Check aliases point to new index
curl -s http://localhost:9200/_alias/evidara-documents-read-dev | jq 'keys'

# Check document count matches
curl -s http://localhost:9200/evidara-documents-read-dev/_count | jq '.count'
```

### Step 4: Clean Up Old Index (Optional)

After confirming the new index is correct:

```bash
# Delete old index (only after verification!)
curl -X DELETE http://localhost:9200/OLD_INDEX_NAME
```

## Procedure: Schema Migration Reindex

When the index mapping has changed:

1. Update the canonical mapping in
   `legal-search/api/src/core/opensearch/documents-index.mapping.ts` (the single
   source of truth consumed by the cutover script, the seed script, and the
   startup bootstrap)
2. Dry-run to verify
3. Execute with `--reindex` to copy data from old → new (with new mapping)
4. Verify document counts
5. Clean up old index

## Procedure: Fresh Reindex (No Data Copy)

When you want to start from a clean index and rebuild from events:

```bash
# Create fresh index without copying data
npx tsx scripts/opensearch-alias-cutover.ts

# Replay events from platform-control to rebuild projections
# Option A: Trigger re-publish of document-processed events
# Option B: Use the Pub/Sub DLQ replay script
```

## Rollback

If something goes wrong after cutover:

```bash
# Point aliases back to old index
curl -X POST "http://localhost:9200/_aliases" -H 'Content-Type: application/json' -d '{
  "actions": [
    {"remove": {"index": "NEW_INDEX", "alias": "evidara-documents-read-dev"}},
    {"remove": {"index": "NEW_INDEX", "alias": "evidara-documents-write-dev"}},
    {"add": {"index": "OLD_INDEX", "alias": "evidara-documents-read-dev"}},
    {"add": {"index": "OLD_INDEX", "alias": "evidara-documents-write-dev", "is_write_index": true}}
  ]
}'
```

## Guardrails

| Check | When |
|-------|------|
| Always dry-run first | Before any production cutover |
| Compare document counts | After reindex, before cleanup |
| Keep old index for 24h | Don't delete immediately |
| Check projection-history | Verify recent events are present |
| Monitor error rates | After cutover via Cloud Monitoring |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSEARCH_NODE` | `http://localhost:9200` | OpenSearch endpoint |
| `OPENSEARCH_ALIAS_READ` | `evidara-documents-read-dev` | Read alias |
| `OPENSEARCH_ALIAS_WRITE` | `evidara-documents-write-dev` | Write alias |
| `OPENSEARCH_USERNAME` | — | Auth username (optional) |
| `OPENSEARCH_PASSWORD` | — | Auth password (optional) |

## Related Resources

- [opensearch-alias-cutover.ts](../../legal-search/api/scripts/opensearch-alias-cutover.ts)
- [OpenSearch GKE rollout runbook](./opensearch-gke-rollout.md)
- [DLQ triage runbook](./dlq-triage-and-replay.md)
- [Alert response playbook](./alert-response-playbook.md)
