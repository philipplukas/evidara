# HITL Rollout, Migration & Re-index Runbook

Owner: Platform team
Last reviewed: 2026-04-25
Last verified: Not yet verified
Applies to: staging, prod

## Scope

Production-safe rollout for the M7–M10 HITL track:

- `corrections` envelope (envelope, lifecycle, canonical IDs)
- commentary insight overlays as first-class search records (`record_kind`)
- canonical `jur_*` / `auth_*` filters on `legal-search`
- supporting OpenSearch mapping change + projection replay
- targeted rescore Temporal workflow (if shipped — see status table below)

The wire shapes consumed by every step are frozen in PR
[#434](https://github.com/philipplukas/evidara/pull/434) — `contracts/manifest.yaml` ≥ 1.7.0,
`platform-control` API ≥ 0.5.0, `legal-search` API ≥ 0.4.0,
`contracts/schemas/corrections.json` present.

This runbook is **forward-looking**: it is published ahead of the
lane PRs (#421 platform overlay, #425 commentary search join, #427
targeted rescore, #428 admin queue, #429 canonical filters, #432
correction metrics, #431 commentary rendering) so the rollout shape
is reviewable now. Sections that depend on unmerged work are marked
**`Resolves on lane completion`** and will be filled in by a follow-up
PR after the lane lands.

Related issues:
[#420](https://github.com/philipplukas/evidara/issues/420) (epic),
[#423](https://github.com/philipplukas/evidara/issues/423) (contracts freeze),
[#430](https://github.com/philipplukas/evidara/issues/430) (this runbook).

## Ownership

- **Primary owner**: Platform on-call.
- **Escalation owner**: Service owner for platform-control + legal-search.
- **Re-index owner**: Search lane owner (legal-search). Pages on alias-swap failure.

## Lane status (kept current; flip to ✅ as lanes land)

| Lane | Issue | Surfaces affected | Status |
|---|---|---|---|
| Contracts freeze | [#423](https://github.com/philipplukas/evidara/issues/423) | `contracts/` | PR [#434](https://github.com/philipplukas/evidara/pull/434) open |
| Platform correction + commentary overlay API | [#421](https://github.com/philipplukas/evidara/issues/421) | `platform-control/` | Resolves on lane completion |
| Commentary records + primary-document join | [#425](https://github.com/philipplukas/evidara/issues/425) | `legal-search/api/`, projection builder | Resolves on lane completion |
| Targeted rescore from correction | [#427](https://github.com/philipplukas/evidara/issues/427) | `platform-control/`, `document-intelligence/` | Resolves on lane completion |
| Admin correction queue + editor | [#428](https://github.com/philipplukas/evidara/issues/428) | `platform-control/admin/` | Resolves on lane completion |
| Canonical `jur_*` filters | [#429](https://github.com/philipplukas/evidara/issues/429) | `legal-search/api/` | Resolves on lane completion |
| Correction metrics dashboard | [#432](https://github.com/philipplukas/evidara/issues/432) | `platform-control/admin/` | Resolves on lane completion |
| Commentary result rendering | [#431](https://github.com/philipplukas/evidara/issues/431) | `legal-search/frontend/` | Resolves on lane completion |

## Pre-flight

Confirm before starting the rollout window:

- [ ] `contracts/manifest.yaml` on `main` is at version ≥ 1.7.0; `platform_control` API ≥ 0.5.0; `legal_search` API ≥ 0.4.0.
- [ ] All lane PRs merged; the per-surface narrow gates are green on `main` (`platform-control` pytest, `platform-control/admin` `npm run check`, `legal-search/api` `npm test`, `legal-search/frontend` `npm run check`).
- [ ] You have `platform_control_dsn` secret access for the target GCP project (or a Cloud SQL Auth Proxy shell).
- [ ] OpenSearch admin credentials for the target environment (re-index step).
- [ ] No active long-running runs that would write to the projection during alias swap. `platform-control` reports `Run.status` filters: `pending` + `running`.
- [ ] You have a 30-minute window. The replay step is the long pole — wall-clock depends on document count; on staging it has historically run in ~10 min.

## Rollout sequence

The lanes deploy bottom-up: contracts → DB schema → APIs → search projection → admin UI. Reordering breaks consumers.

### Step 1 — Apply Alembic migrations on `platform-control`

The corrections + commentary-overlay schema change ships with one or more migrations chained off the current head. The exact head IDs are pinned by the merging lane (#421); fill in below at lane-completion.

```bash
export PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://<user>:<pass>@<host>:5432/<db>"
cd platform-control

uv run alembic current
# Expected pre-rollout head: <pre_corrections_head>  # Resolves on lane completion (#421)

uv run alembic upgrade head --sql > /tmp/upgrade.sql
less /tmp/upgrade.sql
# Expect DDL for: corrections, commentary_insight_overlay (or equivalent),
# any new FK columns into jurisdictions/authorities. Resolves on lane completion (#421).

uv run alembic upgrade head

uv run alembic current
# Expected post-rollout head: <post_corrections_head>  # Resolves on lane completion (#421)
```

**Rollback (Method A — same window):** `uv run alembic downgrade <pre_corrections_head>` if no rows have been written to the new tables. If the API is already taking traffic, prefer Method B below.

### Step 2 — Deploy `platform-control` API

`platform-control` API gains the `/v1/corrections` paths frozen in #434 (operationIds: `createCorrection`, `listCorrections`, `getCorrection`, `updateCorrectionStatus`).

Deploy follows the standard Cloud Run flow already documented in
[`release-rollback.md`](release-rollback.md). Verify the OpenAPI surface
is what you shipped:

```bash
OPERATOR_TOKEN=<staging operator api key>
curl -fsS -H "X-API-Key: $OPERATOR_TOKEN" \
  https://platform-control-staging.<project>.run.app/openapi.json \
  | jq '.info.version, .paths."/v1/corrections" | has("post")'
# Expect: "0.5.0", true
```

**Rollback:** Cloud Run revision pin to the prior SHA (see
[`release-rollback.md` § Method 1](release-rollback.md#method-1-revert-to-previous-revision-fastest)).
Safe even after corrections rows exist — old code ignores them.

### Step 3 — Deploy `platform-control` worker (only if rescore lane shipped)

The targeted rescore Temporal workflow (#427) lives in the platform-control worker. If that lane is in this rollout, redeploy the worker with the new SHA.

Confirm worker registers the new workflow:

```bash
# Resolves on lane completion (#427) — exact workflow name TBD.
# Look for: "registered workflow ... <rescore-workflow-name>" in startup logs.
```

If the rescore lane is **not** in this rollout, skip this step.

### Step 4 — Deploy `legal-search` API

`legal-search` API gains the canonical `jurisdiction_id` / `jurisdiction_ids` / `authority_id` / `authority_ids` query params on `GET /v1/search`, plus commentary-record join behavior in the projection adapter (#425).

Deploy follows the same Cloud Run flow. Verify the new params are accepted and that the API still returns the same total for an ISO-only query (no regression on legacy filters):

```bash
BASE=https://legal-search-staging.<project>.run.app

# Sanity: legacy ISO filter still returns results.
curl -fsS "$BASE/v1/search?q=arbeitsrecht&jurisdiction=CH" | jq '.totalResults'

# New canonical filter should return a comparable, AND-ed set.
curl -fsS "$BASE/v1/search?q=arbeitsrecht&jurisdiction_id=jur_ch_federal" | jq '.totalResults'
```

**Rollback:** Cloud Run revision pin. Safe — old code ignores the new params.

### Step 5 — OpenSearch mapping update + alias swap + projection replay

The projection picks up the new `record_kind`, `jurisdiction_ids`,
`authority_ids`, and `source_document_ids` fields per the contract
freeze. The mapping change is non-additive (new keyword arrays + a
`record_kind` keyword), so we follow the standard alias-cutover from
[`projection-reindex-backfill.md`](projection-reindex-backfill.md):

1. **Build a new versioned index** with the updated mapping.
2. **Reindex** from the current index into the new one.
3. **Cut over** the read + write aliases in a single atomic call.
4. **Verify** doc counts match and a smoke query against the canonical filter returns expected hits.
5. **Hold the old index** for at least 24h before cleanup so a fast revert is possible.

```bash
cd legal-search/api
npx tsx scripts/opensearch-alias-cutover.ts --reindex --dry-run
# Inspect the dry-run output: confirm new index name, source index, and alias targets.

npx tsx scripts/opensearch-alias-cutover.ts --reindex
```

The exact mapping diff (new field types, any analyzer changes) is set
by the projection builder in #425. Resolves on lane completion (#425).

**Rollback (alias revert):**

```bash
# Point the read+write aliases back at the previous index.
npx tsx scripts/opensearch-alias-cutover.ts --revert
# (--revert flag mirrors the cutover idiom; if the script doesn't support it
#  yet, the manual fallback is documented in projection-reindex-backfill.md
#  § Manual alias revert.)
```

If the new mapping silently drops a doc, prefer revert + investigate
over re-running the reindex; reindex twice without alias revert
double-writes.

### Step 6 — Deploy `platform-control/admin`

The admin app gains the correction queue + commentary editor (#428) and the correction metrics dashboard (#432). Deploy the static build to its hosting target.

Smoke: the operator login flow loads the new "Corrections" entry in the
nav. Specific URL/path lives with the lane PR. Resolves on lane completion (#428).

### Step 7 — Deploy `legal-search/frontend`

Commentary result rendering (#431) ships as part of the frontend deploy. No special handling beyond the standard Cloud Run rollout.

## Smoke checklist

Run after **each** deploy step, top to bottom. All checks should pass before proceeding.

### Platform-control corrections — `evidara` CLI or curl

```bash
# 1. Authenticate against private Cloud Run.
source <(bash scripts/mint-cloud-run-tokens.sh staging)
# (See docs/setup/gcp-local-cloud-run-auth.md for first-time setup.)

# 2. Create a correction (round-trip the freeze examples).
evidara corrections create \
  --target-entity-type commentary_insight \
  --target-entity-id ins_01jq7c1ny0ffv8qdr1xwbejqb6 \
  --correction-type field_edit \
  --payload '{"field":"claim","value":"smoke check"}' \
  --rationale "smoke check"
# Expect: 201 with cor_<ulid>.

# 3. List corrections, scoped by status.
evidara corrections list --status pending --limit 5
# Expect: 200 with array of corrections.

# 4. Transition a correction.
evidara corrections update <correction_id> --status applied
# Expect: 200 with applied_at populated.

# Negative: attempting an illegal transition (rejected → applied).
evidara corrections update <correction_id> --status applied
# Expect: 409 illegal-transition.
```

(The exact CLI subcommand names and flags follow the platform-control lane
PR. If the CLI doesn't yet expose `corrections`, the same calls are
straightforward `curl` invocations against the OpenAPI spec frozen in
PR #434. Resolves on lane completion (#421).)

### Legal-search canonical filters

```bash
BASE=https://legal-search-staging.<project>.run.app

# Canonical jurisdiction filter — single + CSV.
curl -fsS "$BASE/v1/search?q=arbeitsrecht&jurisdiction_id=jur_ch_federal" | jq '.totalResults'
curl -fsS "$BASE/v1/search?q=arbeitsrecht&jurisdiction_ids=jur_ch_zh,jur_ch_be" | jq '.totalResults'

# Canonical authority filter.
curl -fsS "$BASE/v1/search?q=arbeitsrecht&authority_id=auth_fedlex" | jq '.totalResults'

# AND-ing canonical with legacy ISO must not over-narrow to zero on a query
# that returns >0 results without filters.
curl -fsS "$BASE/v1/search?q=arbeitsrecht&jurisdiction=CH&jurisdiction_id=jur_ch_federal" | jq '.totalResults'

# Commentary records appear as their own search-result rows once the join lands.
curl -fsS "$BASE/v1/search?q=arbeitsrecht" \
  | jq '.results[] | select(.type == "commentary") | {id, title}'
# Resolves on lane completion (#425, #431).
```

### OpenSearch projection sanity

```bash
# Doc count delta — old vs new index should match.
curl -s http://<opensearch-host>/<old_index>/_count | jq '.count'
curl -s http://<opensearch-host>/<new_index>/_count | jq '.count'
# Expect: equal.

# Spot a record_kind=commentary_insight document in the new index.
curl -s -X POST http://<opensearch-host>/<new_index>/_search \
  -H 'Content-Type: application/json' \
  -d '{"query":{"term":{"record_kind":"commentary_insight"}}, "size":1}' \
  | jq '.hits.total'
# Expect: > 0 once the projection builder is wired (Resolves on lane completion (#425)).
```

## Rollback strategy

| Surface | Method | Notes |
|---|---|---|
| `platform-control` API | Cloud Run revision pin (Method 1 in `release-rollback.md`) | Safe even with corrections rows present. Old code ignores them. |
| `platform-control` worker | Cloud Run revision pin | Skip if no worker change in this rollout. |
| `legal-search` API | Cloud Run revision pin | Safe — old code ignores new query params. |
| `legal-search/frontend` | Cloud Run revision pin / static-host previous build | Safe. |
| `platform-control/admin` | Cloud Run revision pin / static-host previous build | Safe. |
| Alembic migration | `alembic downgrade <pre_corrections_head>` | Only safe **before** corrections rows exist. After, see Method B below. |
| OpenSearch index | `opensearch-alias-cutover.ts --revert` | Atomic alias swap back. Hold old index for ≥ 24h. |

**Method B — partial rollback when corrections rows exist:**

If the API has been live and operators have raised corrections, do **not** downgrade Alembic; the FK from corrections → upstream entities will drop rows. Instead:

1. Revert the API revision (Cloud Run Method 1).
2. Leave the corrections table in place; the old API simply doesn't expose it.
3. File a follow-up to clean up orphan rows on the next forward roll.

## Replay strategy

Replay strategy reuses
[`projection-reindex-backfill.md`](projection-reindex-backfill.md) and
[`staging-projection-replay.md`](staging-projection-replay.md). Two
scenarios this rollout introduces:

1. **Mapping-change replay** — Step 5 above. Single full reindex with
   alias cutover. Already covered.
2. **Targeted rescore replay** — when an operator raises a `rescore_request`
   correction, the platform-control worker (#427) emits a `rescore`
   workflow that re-processes the targeted document and the projection
   builder picks up the change incrementally. No global reindex needed.
   Resolves on lane completion (#427).

If replay diverges from doc count or mapping shape mid-rollout, abort
the cutover, hold the read alias on the old index, and triage via
[`event-tracing-queries.md`](event-tracing-queries.md).

## Post-flight

- [ ] Migration summary (before/after Alembic head, wall time, row counts) posted to Linear.
- [ ] Smoke checklist green for both `platform-control` and `legal-search`.
- [ ] OpenSearch new-index doc count matches old-index count; canonical filter sample query returns expected hits.
- [ ] Update the **Last verified:** header of this runbook with the date and environment.
- [ ] If any "Resolves on lane completion" placeholders are now resolvable, fold them into the same PR or a follow-up.

## PR completion sync surfaces (per AGENTS.md)

This runbook PR is **docs-only**. Sync surfaces touched:

- **Code**: none.
- **Tests**: none.
- **Contracts**: none — references only to the freeze landing in PR #434.
- **Docs**: this file + a link from
  [`docs/components/platform-control.md`](../components/platform-control.md)
  and
  [`docs/components/legal-search.md`](../components/legal-search.md)
  pointing operators at this runbook for the HITL rollout window.
- **Architecture**: none — no Structurizr or ADR change. The contract
  shapes are codified in PR #434; this runbook is a pure operator guide.

## Resolves on lane completion (tracking list)

The placeholders below resolve as their lane PRs land:

- Pre-rollout / post-rollout Alembic head IDs (#421).
- Exact rescore Temporal workflow name + worker registration log line (#427).
- Final OpenSearch mapping diff for the projection (#425).
- Admin nav path / URL for the corrections queue (#428).
- `evidara` CLI subcommand surface for `corrections` (#421).
- `--revert` flag on `opensearch-alias-cutover.ts` if the lane introduces it; otherwise keep the manual fallback link.

A follow-up PR (or the merging lane PR itself) should remove each "Resolves on lane completion" sentinel as the value lands.
