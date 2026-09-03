# Projection Reindex & Backfill Runbook

Owner: Platform team
Last reviewed: 2026-09-03
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

Rebuilding only ever *adds*. The backfill upserts on `document_id`, so it cannot remove
an indexed document whose canonical row is gone — see
[Reconcile](#procedure-reconcile--remove-indexed-documents-canonical-does-not-back)
for the other direction of the same invariant.

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

## Procedure: Reconcile — remove indexed documents canonical does not back

**Use this when the index contains documents that canonical Delta no longer has** —
test artifacts, contentless stubs, orphans left by an earlier run, anything a user can
search for but the platform cannot account for.

The Delta backfill above cannot do this. It is idempotent **by upsert on
`document_id`**, so it only ever adds or overwrites; a projection whose canonical row
is gone survives every rebuild. Reconciliation is the other half of ADR-0005's
"the index is derived from canonical": it diffs *index minus canonical* and de-indexes
the remainder.

### What reconcile can and cannot remove

It removes **index-minus-canonical, and nothing else**. That boundary matters most for
duplicates, where it is easy to assume more:

| Case | Removable here? |
|---|---|
| Indexed document with no `published_documents` row | Yes — this is what the job is for |
| Duplicate whose *stale* copy is index-only | Yes — the stale id is an orphan |
| Duplicate where **both** ids have canonical rows | **No** — neither id is an orphan |

The third row is the #652 case: the identity key changed, so a law acquired before the
fix and again after it has two `document_id`s. If both were processed to canonical, both
have `published_documents` rows, and **reconcile deletes neither**.

> **Backfill + reconcile is not a duplicate remediation.** The backfill replays each
> canonical row under the `document_id` *stored on the row* — it does not recompute
> identity — so a rebuild reproduces both ids verbatim, and reconcile then finds no
> orphan to remove. Running the pair on a canonical-side duplicate cleans up unrelated
> orphans and leaves the duplicate exactly where it was.

Removing a canonical-side duplicate is a different, heavier sequence, and it starts on
the canonical side:

1. Decide which `document_id` the **current** identity key mints (`_document_identity_key`
   in `document_intelligence/pipeline.py` — it keys on the bundle's `upstream_locator`).
2. Delete the stale document's rows from canonical Delta (`published_documents` **and**
   `published_sections`).
3. Reconcile — the stale id is now index-minus-canonical, so it becomes removable.
4. Re-acquire the document through the platform if the surviving copy is not the one you
   want to keep.

Confirm which case you are in before planning the work — the dry run below lists exactly
what is orphaned, and a duplicate that does not appear in `orphan_document_ids` is
canonical-side:

```bash
document_intelligence_projection_reconcile | jq '.orphan_document_ids'
```

```text
   canonical truth (Delta)        derived view (OpenSearch)
   published_documents            documents-write
            │                              │
            │  backfill: canonical-index   │  GET /v1/projections/documents
            │  (adds what is missing)      │  (enumerates what is indexed)
            ▼                              ▼
        ───────────  document_intelligence_projection_reconcile  ───────────
                        POST /v1/projections/events/document-withdrawn
                        (deletes projection + sections + citations)
```

Removal goes through the **existing** `document.withdrawn` path, so it inherits
legal-search's revision guard: if a live event has re-projected a newer revision of a
document since enumeration, the withdrawal is marked `stale` and dropped.

### Step 1: Dry run (this is the default)

The job deletes nothing unless `--delete-orphans` is passed.

```bash
cd document-intelligence
export DI_SURFACES_ROOT_URI=s3://evidara-lakehouse/canonical
export DI_S3_ENDPOINT_URL=... DI_S3_ACCESS_KEY_ID=... DI_S3_SECRET_ACCESS_KEY=...
export LEGAL_SEARCH_API_URL=http://legal-search-api:3001
export LEGAL_SEARCH_API_KEY=...          # only if the projections endpoints are guarded
document_intelligence_projection_reconcile
```

```json
{
  "canonical_documents": 2,
  "deleted": 0,
  "dry_run": true,
  "indexed_scanned": 24,
  "orphan_document_ids": ["doc_3xky3kc486ey3ycm9354q8ccs1", "…"],
  "orphaned": 22,
  "skipped_unwithdrawable": 0
}
```

**Read `orphan_document_ids` before going further.** These documents disappear from
search. Spot-check a few against canonical:

```bash
curl -s "$LS_URL/v1/documents/<one-of-the-ids>" | jq '.title'
```

`skipped_unwithdrawable` counts orphans whose index row lacks the provenance ids a
contract-valid `document.withdrawn` needs (`processing_manifest_id`, `source_id`,
`source_version_id`, `run_id`). The job will not invent them; those ids are listed in
`unwithdrawable_document_ids` and must be deleted by hand from OpenSearch.

### Step 2: Delete

```bash
document_intelligence_projection_reconcile --delete-orphans
```

Two guardrails run **before** anything is deleted, both aimed at the same failure —
a canonical side that reads as empty because it is misconfigured, not because the
index is wrong:

| Guardrail | Behaviour |
|---|---|
| Canonical enumerated 0 documents | Refuses outright. Check `DI_SURFACES_ROOT_URI` / `DI_S3_*`. |
| Orphans exceed `--max-orphan-fraction` (default `0.25`) | Refuses and prints the diff. Raise the bound only after reading the dry-run list. |

The fraction is of the *indexed* count, so a small index trips the bound early: 4 orphans
out of 6 indexed documents is `0.67` and is refused, however obviously right the diff is.
A large legitimate cleanup therefore needs the bound raised deliberately, e.g. the
22-of-24 case above:

```bash
document_intelligence_projection_reconcile --delete-orphans --max-orphan-fraction 1.0
```

`--resume` continues from the last withdrawn `document_id` after an interruption.

### Step 3: Verify

```bash
# Index count should now equal the canonical count from the dry run
curl -s "$OS/evidara-documents-read-dev/_count" | jq '.count'

# The withdrawals are auditable in projection history
curl -s "$LS_URL/v1/projections/events/history?status=applied&limit=50" \
  | jq '[.data[] | select(.eventType == "document.withdrawn")] | length'
```

If the count is still high, re-run the dry run: a document re-projected by live traffic
between enumeration and withdrawal is dropped as `stale` by design.

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
| Read `orphan_document_ids` before `--delete-orphans` | Reconcile removes user-visible documents; the dry run is the only preview |
| Never raise `--max-orphan-fraction` to clear a refusal | A near-total diff usually means canonical is misconfigured, not that the index is wrong |
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

Reconcile (`document_intelligence_projection_reconcile`) takes the same environment,
plus:

| Variable | Default | Description |
|----------|---------|-------------|
| `DI_RECONCILE_CHECKPOINT_PATH` | `/tmp/evidara-projection-reconcile.checkpoint` | Resume cursor for `--resume` |

Useful flags: `--delete-orphans` (**required to delete anything**),
`--max-orphan-fraction`, `--limit N`, `--resume`, `--after-document-id <id>`,
`--page-size`.

## Related Resources

- [ADR-0005: Search Strategy](../adr/0005-search-strategy.md) — why the index is derived, not authoritative
- [delta_projection_backfill.py](../../document-intelligence/src/document_intelligence/jobs/delta_projection_backfill.py)
- [projection_reconcile.py](../../document-intelligence/src/document_intelligence/jobs/projection_reconcile.py)
- [opensearch-alias-cutover.ts](../../legal-search/api/scripts/opensearch-alias-cutover.ts)
- [OpenSearch GKE rollout runbook](./opensearch-gke-rollout.md)
- [DLQ triage runbook](./dlq-triage-and-replay.md)
- [Alert response playbook](./alert-response-playbook.md)
