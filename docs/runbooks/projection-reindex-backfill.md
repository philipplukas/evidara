# Projection Reindex & Backfill Runbook

Owner: Platform team
Last reviewed: 2026-07-13
Last verified: Not yet verified
Applies to: dev, staging, prod

## Overview

This runbook documents how to safely perform reindex and backfill operations
on the legal-search projection index (OpenSearch). These operations are needed
when the index is lost, the index mapping changes, data corruption occurs, or
after a major schema migration.

**Canonical truth is Delta, not OpenSearch** (ADR-0005). The search index is a
*derived* view: `published_documents` / `published_sections` on MinIO/S3 are the
system of record, and the index can always be rebuilt from them. That rebuild is
the [Delta backfill](#procedure-rebuild-from-canonical-delta-disaster-recovery),
and it is the procedure to reach for when the index is gone.

> **Do not rely on NATS JetStream replay to rebuild the index.** Restarting
> `projection-bridge` re-delivers whatever `document.processed` events JetStream
> still retains, which *looks* like a rebuild but is a side effect of a queue's
> retention policy. It silently loses every document older than the retention
> window, and — because the replayed events are re-projected without their
> canonical bodies — the documents it does recover can land as degraded shells
> (`sections_count: 0`, fallback titles). Rebuild from Delta instead.

## Prerequisites

- `gcloud` authenticated, `npx` available
- Access to the OpenSearch cluster
- Knowledge of which environment you're targeting
- For a Delta rebuild: read access to the canonical object store (MinIO/S3), and
  network access from the backfill job to the legal-search projections endpoint

## Architecture

```text
   canonical truth (Delta on MinIO/S3)
   published_documents + published_sections
                  │
                  │  document_intelligence_delta_projection_backfill
                  │  (replays each row as a document.processed event)
                  ▼
        legal-search projections API ──────► write alias ──► index-v2 (new)
                  ▲                                              │
                  │                                              │ promote
   live NATS document.processed events                           ▼
                                                  read alias ──► index-v2
```

Two rebuild sources, two different tools:

| Source | Tool | Use when |
|---|---|---|
| Previous **index** | `opensearch-alias-cutover.ts --reindex` | The old index is healthy; you only want a new mapping. Fast (server-side `_reindex`). |
| Canonical **Delta** | `document_intelligence_delta_projection_backfill` | The index is lost/empty/degraded, or you want to re-derive projections from truth. The only path that works when OpenSearch has nothing to read from. |

The cutover script creates a new versioned index and atomically swaps the
read/write aliases. Zero-downtime.

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

### How a broken alias surfaces

A missing read alias is a total outage of search, so it fails loudly (#551) —
it is never reported as "no results":

- `GET /v1/search` and `GET /v1/search/context` return **503** with an ERROR log
  (`index_not_found_exception` / connection failure). A query that executed and
  matched nothing still returns **200** with an empty `results` array.
- `GET /health/ready` returns **503** with
  `checks.documents_read_alias.status = "error"` when the read alias does not
  resolve to an index. Check it first when search looks empty:

  ```bash
  curl -s ${LS_URL}/health/ready | jq '.checks.documents_read_alias'
  ```

## Procedure: Rebuild from canonical Delta (disaster recovery)

**Use this when the index is missing, empty, or degraded** — i.e. whenever
OpenSearch has nothing trustworthy to reindex *from*. This is the procedure that
makes ADR-0005's "rebuilt from canonical source" real.

The job walks `published_documents` on Delta, reconstructs the
`document.processed` event each row originally produced, and POSTs it to the same
idempotent legal-search projections endpoint the live NATS bridge uses. It is
therefore *not* a second projection implementation — it replays canonical rows
through the production code path.

### Step 0: Check the preconditions

The backfill rebuilds a *full* projection only if legal-search can fetch each
document's canonical body back from the DI read API. If it can't, documents still
index — but as degraded shells (`sections_count: 0`, fallback titles). Verify
both sides are wired before you start:

```bash
# legal-search must know where the DI read API is:
kubectl -n evidara set env deploy/legal-search-api --list | grep DOCUMENT_INTELLIGENCE_BASE_URL

# ...and the DI read API must be Delta-backed (not fixture-backed):
kubectl -n evidara set env deploy/document-intelligence-document-service --list \
  | grep -E 'DI_SURFACES_ROOT_URI|DI_PUBLISHED_DOCUMENTS_URI'

# Sanity-check that canonical truth is actually readable:
curl -s "$DI_URL/v1/documents/<known-doc-id>/lean" | jq '.sections | length'   # want > 0
```

### Step 1: Dry run

Enumerate canonical Delta and build events, but POST nothing:

```bash
cd document-intelligence
export DI_SURFACES_ROOT_URI=s3://evidara-lakehouse/canonical
export DI_S3_ENDPOINT_URL=... DI_S3_ACCESS_KEY_ID=... DI_S3_SECRET_ACCESS_KEY=...
document_intelligence_delta_projection_backfill --dry-run
```

The summary tells you how much truth exists and whether any rows are unusable:

```json
{
  "applied": 1284,
  "dry_run": true,
  "invalid_document_ids": [],
  "rejected": 0,
  "scanned": 1284,
  "skipped_invalid": 0
}
```

### Step 2: Backfill into the write alias

```bash
export LEGAL_SEARCH_API_URL=http://legal-search-api:3001
export LEGAL_SEARCH_API_KEY=...           # only if the projections endpoint is guarded
document_intelligence_delta_projection_backfill --resume
```

This is safe to run **while the read alias is serving live traffic**:

- Writes land on the write alias; the read alias is never touched.
- The projection upserts on `document_id`, so re-running converges rather than
  duplicating. Interrupt and re-run it freely.
- If a live event has already projected a *newer* revision of a document, the
  endpoint's revision guard marks the backfill event `stale` and drops it — a
  concurrent live update always wins the race.
- `--resume` continues from the last checkpointed `document_id`, so an
  interrupted run does not redo completed work.

### Step 3: Verify the rebuild is not degraded

Document count alone is not enough — check the projections carry their canonical
bodies (this is what distinguishes a real rebuild from a JetStream replay):

```bash
# Total documents rebuilt
curl -s "$OS/evidara-documents-read-dev/_count" | jq '.count'

# Documents that came back as shells — should be 0
curl -s "$OS/evidara-documents-read-dev/_count" -H 'Content-Type: application/json' \
  -d '{"query":{"term":{"sections_count":0}}}' | jq '.count'
```

If the shell count is non-zero, Step 0's preconditions were not met: fix the DI
read API wiring and re-run the backfill (it will overwrite the shells in place).

## Procedure: Delta-sourced versioned reindex (zero-downtime)

Use when you need a **new mapping** *and* the projections must be re-derived from
canonical truth (rather than copied from a possibly-degraded old index).

`_reindex` cannot help here — it can only copy what OpenSearch already has. So
the write alias is staged onto the new index first, the backfill fills it from
Delta, and reads are promoted only once it's populated.

```bash
cd legal-search/api

# 1. Create the new versioned index and move ONLY the write alias to it.
#    Reads keep serving the old index, so users see nothing.
npx tsx scripts/opensearch-alias-cutover.ts --stage-write
#    → prints the staged index name, e.g. evidara-documents-read-dev-20260713120000

# 2. Rebuild the staged index from canonical Delta (writes follow the write alias).
document_intelligence_delta_projection_backfill --resume

# 3. Promote reads onto the staged index once it is populated.
#    This refuses to promote an index containing 0 documents.
npx tsx scripts/opensearch-alias-cutover.ts --promote-read --index <staged-index>
```

During the window between (1) and (3), live `document.processed` events also land
in the staged index (they follow the write alias), so no live update is lost.
Reads continue to serve the old index until you promote.

Rollback before promotion is trivial: re-point the write alias at the old index
(`--promote-read` has not run, so reads never moved).

## Procedure: Full Reindex (from the previous index)

Use when the current index is **healthy** and you only need a new mapping — this
is the fast path (server-side `_reindex`, no re-derivation from Delta).

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

When you want to start from a clean index and rebuild it from canonical truth:

```bash
# Create a fresh index and point both aliases at it (no data copied)
npx tsx scripts/opensearch-alias-cutover.ts

# Rebuild it from canonical Delta
document_intelligence_delta_projection_backfill --resume
```

For a rebuild with **no read-side gap**, prefer the
[Delta-sourced versioned reindex](#procedure-delta-sourced-versioned-reindex-zero-downtime)
above — it keeps reads on the old index until the new one is populated.

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
| Always dry-run first | Before any production cutover or backfill |
| Compare document counts | After reindex, before cleanup |
| Check `sections_count: 0` is empty | After a Delta backfill — a non-zero count means projections came back as shells |
| Keep old index for 24h | Don't delete immediately |
| Check projection-history | Verify recent events are present |
| Monitor error rates | After cutover via Cloud Monitoring |
| Never rebuild from JetStream replay | It silently drops everything past the retention window |

## Environment Variables

Cutover script (`legal-search/api`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSEARCH_NODE` | `http://localhost:9200` | OpenSearch endpoint |
| `OPENSEARCH_ALIAS_READ` | `evidara-documents-read-dev` | Read alias |
| `OPENSEARCH_ALIAS_WRITE` | `evidara-documents-write-dev` | Write alias |
| `OPENSEARCH_USERNAME` | — | Auth username (optional) |
| `OPENSEARCH_PASSWORD` | — | Auth password (optional) |

Delta backfill (`document_intelligence_delta_projection_backfill`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DI_SURFACES_ROOT_URI` | — | Canonical surface root (or set `DI_PUBLISHED_DOCUMENTS_URI` / `DI_PUBLISHED_SECTIONS_URI` explicitly) |
| `DI_S3_ENDPOINT_URL` | — | MinIO/S3 endpoint holding the Delta tables |
| `DI_S3_ACCESS_KEY_ID` / `DI_S3_SECRET_ACCESS_KEY` | — | Object store credentials |
| `LEGAL_SEARCH_API_URL` | — | legal-search base URL (projections endpoint derived from it) |
| `LEGAL_SEARCH_API_KEY` | — | `X-API-Key` for the projections endpoint (optional) |
| `DI_BACKFILL_CHECKPOINT_PATH` | `/tmp/evidara-delta-projection-backfill.checkpoint` | Resume cursor for `--resume` |

Useful flags: `--dry-run`, `--limit N`, `--resume`, `--after-document-id <id>`,
`--max-retries`, `--retry-backoff-seconds`.

## Related Resources

- [ADR-0005: Search Strategy](../adr/0005-search-strategy.md) — why the index is derived, not authoritative
- [delta_projection_backfill.py](../../document-intelligence/src/document_intelligence/jobs/delta_projection_backfill.py)
- [opensearch-alias-cutover.ts](../../legal-search/api/scripts/opensearch-alias-cutover.ts)
- [OpenSearch GKE rollout runbook](./opensearch-gke-rollout.md)
- [DLQ triage runbook](./dlq-triage-and-replay.md)
- [Alert response playbook](./alert-response-playbook.md)
