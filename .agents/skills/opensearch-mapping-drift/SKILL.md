---
name: opensearch-mapping-drift
description: Add a field to the documents index, add a new index-creation path, or diagnose a search/facet/filter that returns nothing without erroring. Use when a `group_by` returns empty buckets, a `terms` filter matches nothing, `in_force_at` seems inert, a query "works locally but not in production", or when adding a producer that creates or PUTs the documents index. Covers the one source of truth, first-writer-wins, why a missing field is silent rather than an error, the PRODUCERS registry, and the one fix that is never allowed.
---

# Documents-index mapping: drift, and the fix that is never allowed

The failure this prevents: **a feature that reports success while doing
nothing.** OpenSearch does not error on a field that is not in the mapping — an
aggregation over an absent field returns **empty buckets**, and a `terms` or
`range` filter over one **matches nothing**. So a drifted index presents as a
query bug, for months.

Mapping drift specifically has shipped three times: **#675** (a hand-maintained
copy in a shell script), **#713** (a mapping-less `PUT` in the GCP runtime
tfvars), and the live measurement on 2026-07-29 that found `documents-000001`
missing five mapped fields — `level`, `in_force_from`, `in_force_until`,
`delegates_to`, `subordinate_to`
(`.github/workflows/opensearch-mapping-drift.yml:12-19`). `group_by=level` and
ADR-0033's `in_force_at` were both silently inert in production. #728 is a
different mechanism with the same signature; §5 tells them apart.

## 1. The rule, and the one fix that is never allowed

**One source of truth:**
`legal-search/api/src/core/opensearch/documents-index.mapping.ts`
(`DOCUMENTS_INDEX_PROPERTIES` `:74`, `DOCUMENTS_INDEX_ANALYSIS` `:45`,
`documentsIndexDefinition()` `:161`).

**When a live index disagrees with the canonical mapping, fix the index.** Never
weaken the query to match the drift.

This is not a style preference. #675 was *first* "fixed" by changing the
aggregations to bare field names so they would resolve against the drifted index
— which made the code match the drift and would have broken facets against any
correctly-created index. `mapping-drift.integration.spec.ts:9-22` encodes the
asymmetry that makes that fix unreachable: creation must be canonical, **and** the
detector must still report the historical drifted shape as drift. A detector that
reports "no drift" on a drifted index is worse than none, because it launders the
drift as canonical.

**Index creation is first-writer-wins.** A second creation path does not merely
disagree with the canonical one — it silently *wins* over it. That is why a
parallel copy is not a duplication smell here; it is a live defect waiting for a
cold start.

## 2. Every producer, and where it derives from

| Producer | How it derives |
|---|---|
| Runtime startup (`main.ts` → `bootstrapDocumentsIndex`) | directly, via `createDocumentsIndex()` in `documents-bootstrap.ts:140` |
| Versioned cutover (`legal-search/api/scripts/opensearch-alias-cutover.ts`) | the same `createDocumentsIndex()` |
| Non-TypeScript producers (e.g. `scripts/validate-tar89-metadata-local.sh`) | the generated `scripts/opensearch/documents-index.mapping.json` |

Regenerate the JSON with `npm run mapping:generate` in `legal-search/api`. It is
drift-gated byte-for-byte by
`src/core/opensearch/documents-index.mapping-json.spec.ts`, which also asserts the
`.keyword` sub-fields the facet aggregations target — the exact shape #675's
drifted copy lacked.

**A producer that cannot be added to `PRODUCERS` in
`mapping-drift.integration.spec.ts:122` is by definition drifting.** If you are
adding a creation path, add it to that array; if you cannot, that is the finding.

## 3. Detecting drift

Two halves, and they answer different questions. Do not accept one as the other.

**The creation path (CI-runnable, no cluster):**

```bash
cd legal-search/api && npm run test:integration   # needs a running Docker daemon
```

`mapping-drift.integration.spec.ts` runs every `PRODUCERS` entry against a real
OpenSearch Testcontainer. It proves a *freshly bootstrapped* index is correct and
says nothing about the index actually serving production.

**The live index (needs a reachable cluster):**

```bash
cd legal-search/api
OPENSEARCH_NODE=http://127.0.0.1:9200 OPENSEARCH_INDEX=documents-read \
  npm run mapping:check-drift
```

Exits 1 on drift, 0 when the live index satisfies the canonical mapping; exits 2
when `_mapping` itself fails. It is **deliberately not** part of `npm run check`,
because that gate must stay runnable with no cluster reachable
(`legal-search/api/scripts/check-opensearch-mapping-drift.ts:30-32`). Against an
alias it checks *every* physical index behind it — a half-migrated alias is
exactly the state worth catching.

In CI the live half is `.github/workflows/opensearch-mapping-drift.yml` — daily at
04:15 UTC plus `workflow_dispatch` with an `opensearch_index` input. It **must**
run on an in-cluster ARC runner: the OpenSearch service is ClusterIP-only with no
ingress, so a GitHub-hosted runner fails with `fetch failed`.

## 4. Fixing a drifted live index

The procedure is in `docs/runbooks/projection-reindex-backfill.md`. The
zero-downtime shape (§"Delta-sourced versioned reindex"):

```bash
cd legal-search/api
npx tsx scripts/opensearch-alias-cutover.ts --stage-write   # prints the staged index name
# rebuild the staged index from canonical Delta — reads keep serving the old index
npx tsx scripts/opensearch-alias-cutover.ts --promote-read --index <staged-index>
```

`--dry-run` is available and `--promote-read` refuses to promote an index holding
zero documents. Source the rebuild from **canonical Delta**, not from the previous
index: OpenSearch's own `_reindex` cannot help when the old index is gone or when
its contents are degraded (`opensearch-alias-cutover.ts:14-21`, ADR-0005).

Judgement calls this procedure does not make for you:

- **Whether to reindex or recreate** depends on whether the old index's contents
  are trustworthy. If the drift means fields were never populated, copying from
  the old index copies the hole.
- **Promoting reads is user-visible.** Do it deliberately, and verify the staged
  index is populated first — the runbook's Step 3 checks for shells.
- **Production cutovers are an operator decision.** Do not run one against a
  live environment on your own initiative; report the drift and the remedy.

## 5. Before you report a query as broken

Check, in this order — each is silent, and each has shipped:

1. **Is the field in the live mapping?** `npm run mapping:check-drift`. Empty
   buckets are the signature.
2. **Is the field populated?** A mapped field nothing writes behaves identically
   to a missing one at query time.
3. **Does the query parameter reach the handler at all?** #728: `import type` on a
   controller DTO erases the class, so `ValidationPipe` hands the handler an empty
   object and every query parameter is silently dropped **in the built app only**.
   No Vitest layer can see it. `npm run test:compiled` is the layer that can.

All three present as "the filter does nothing". Naming the wrong one wastes the
fix.

## Boundaries

- **Never weaken a query, an aggregation, or an assertion to match a drifted
  index.** Fix the index. This is the single rule this skill exists for.
- **Never hand-maintain a second copy of the mapping.** Derive it, and register
  the producer.
- **Never change the canonical mapping without regenerating the JSON**
  (`npm run mapping:generate`) — the byte-for-byte gate will catch it, but the
  parallel copy is what caused #675 in the first place.
- **Do not claim a mapping fix is live because CI is green.** The integration
  spec guards the creation path only. Only `mapping:check-drift` against the
  actual cluster says anything about the index serving traffic.

## Reference

- `legal-search/api/src/core/opensearch/documents-index.mapping.ts` — the source of truth
- `legal-search/api/src/core/opensearch/documents-bootstrap.ts` — `createDocumentsIndex()`, the one creator
- `legal-search/api/src/core/opensearch/mapping-drift.integration.spec.ts` — `PRODUCERS`, and the drifted-shape fixture
- `legal-search/api/scripts/check-opensearch-mapping-drift.ts` — the live comparator and its own account of #675/#713
- `.github/workflows/opensearch-mapping-drift.yml` — the live gate, and the measurement that justified it
- `docs/runbooks/projection-reindex-backfill.md` — reindex, reconcile, and versioned cutover procedures
- AGENTS.md, "The documents-index mapping has one source of truth" — the standing rule
