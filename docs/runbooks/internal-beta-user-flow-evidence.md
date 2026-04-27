# Internal Beta User-Flow Evidence

Owner: Platform / legal-search
Last reviewed: 2026-04-27
Last verified: 2026-04-27
Applies to: Hetzner `evidare-staging` internal beta

## Purpose

This is the canonical one-week internal beta query/evidence packet while GCP
billing is disabled. It proves the smallest useful user promise:

`seeded document -> searchable result -> trusted detail -> HITL correction/rescore -> metrics -> recoverable staging state`

Use this packet before broader corpus or ranking claims. The current beta corpus
is intentionally small and deterministic.

## Beta Corpus

| Document ID | Source | Expected user-facing evidence |
| --- | --- | --- |
| `doc_6vfta1cd5xy642g7eb59j8wkfm` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 101 snapshot; searchable title `Federal Constitution of the Swiss Confederation`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_67b9202dsxm52sa36dsfvcm6bt` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 220 snapshot; searchable title `Code of Obligations`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_20djzpnf2yytwg9k74zyzjdeta` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 272 snapshot; searchable title `Civil Procedure Code`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_2em3ky37mw9tm7hxh5nkw0zkh7` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 235.1 snapshot; searchable title `Federal Act on Data Protection`, `type=law`, Fedlex subtitle, useful metadata |

Query pack:

- [`scripts/fixtures/internal-beta-staging-queries.txt`](../../scripts/fixtures/internal-beta-staging-queries.txt)
- [`scripts/fixtures/internal-beta-staging-expected.tsv`](../../scripts/fixtures/internal-beta-staging-expected.tsv)
- [`scripts/fixtures/internal-beta-staging-documents.tsv`](../../scripts/fixtures/internal-beta-staging-documents.tsv)
- [`scripts/fixtures/internal-beta-staging-withdrawn-documents.txt`](../../scripts/fixtures/internal-beta-staging-withdrawn-documents.txt)
- Expected result: the nine beta queries return their named source-derived
  document(s) in top 5. The broad `Fedlex` row expects all four beta documents
  in top 5.
- `q=*` is the corpus-health control. It must return `totalResults=4`, and the
  visible document set must be exactly the four source-derived Fedlex documents
  listed above.
- The old synthetic beta document IDs are tombstones: detail reads must return
  `404` from legal-search.
- Detail reads for the four source-derived documents must show a
  non-placeholder title, controlled `law` type, Fedlex subtitle, at least four
  metadata rows, and `content`, `sections`, `citations`, and `details` tabs.

This corpus is enough for the internal beta trust loop. It is not evidence that
broader legal relevance is solved.

## Operator Flow

Run against the Hetzner cluster with `kubectl` access. Commands must not print
Kubernetes Secret values.

1. Verify runtime health:

   ```bash
   kubectl -n argocd get app rocky-agents-staging
   kubectl -n evidare-staging get deploy \
     platform-control-api platform-control-worker legal-search-api legal-search-frontend \
     document-intelligence-consumer document-intelligence-document-service
   kubectl -n evidare-staging get job evidara-di-seed
   ```

2. Verify DI seed surfaces:

   ```bash
   kubectl -n evidare-staging exec deploy/platform-control-worker -- sh -lc 'python - <<PY
   import os, sys
   from deltalake import DeltaTable
   for name in ["published_documents", "published_sections", "processing_manifests"]:
       table = DeltaTable(f"file:///var/lib/evidara/surfaces/{name}").to_pyarrow_table()
       print(f"{name}: {table.num_rows} rows")
   sys.stdout.flush()
   os._exit(0)
   PY'
   ```

3. Verify search and detail:

   ```bash
   kubectl -n evidare-staging port-forward svc/legal-search-api 18080:8080
   EVIDARA_LEGAL_SEARCH_URL=http://127.0.0.1:18080 \
     ./scripts/check-internal-beta-query-pack.sh
   # Optional Markdown top-3 table for a Linear comment or release note:
   EVIDARA_LEGAL_SEARCH_URL=http://127.0.0.1:18080 \
     EVIDARA_LEGAL_SEARCH_TOKEN=dummy \
     ./scripts/run-staging-relevance-query-pack.sh \
     scripts/fixtures/internal-beta-staging-queries.txt
   curl -fsS http://127.0.0.1:18080/v1/documents/doc_6vfta1cd5xy642g7eb59j8wkfm |
     jq '{id, title, type, subtitle, metadata, tabs}'
   ```

4. Verify HITL rescore:

   ```bash
   ./scripts/smoke-hetzner-hitl-rescore.sh
   ```

5. Verify backup/restore evidence:

   Use the Rocky restore drill runbook and PR evidence. Acceptance requires a
   completed CNPG backup plus a restore drill result that does not expose secret
   values.

## Acceptance

- `rocky-agents-staging` is `Synced` and `Healthy`.
- `evidara-di-seed` is complete and Delta surfaces are readable.
- The expected-query pack returns each named source-derived document in top 5,
  and `q=*` returns exactly the four-document beta corpus.
- Old synthetic document IDs return `404` from legal-search detail.
- Detail shows a non-placeholder title, controlled `law` type, Fedlex subtitle,
  at least four metadata rows, and content/sections/citations/details tabs.
- HITL rescore ends `changed` or `unchanged`; metrics increment the matching
  bucket.
- CNPG restore drill evidence exists, or the packet is marked blocked on backup
  proof.

## Current Evidence

2026-04-27 live check:

- Argo: `Synced Healthy Succeeded` at
  `4ad26f26ca071eb5ef72c1caa765ba2b1e825e0b`.
- `evidara-di-seed`: complete, `corpus_size=4`, all four legacy synthetic
  projection withdrawals applied.
- Delta rows: `published_documents=8`, `published_sections=16`,
  `processing_manifests=8`. The extra four rows are preserved historical DI
  surface rows; legal-search visibility is controlled by withdrawal events.
- Query gate: [`scripts/check-internal-beta-query-pack.sh`](../../scripts/check-internal-beta-query-pack.sh)
  passed; `q=*` returned exactly the four source-derived documents.
- Legacy synthetic details: old document IDs return `404` from legal-search.
- Detail trust: all four source-derived documents have non-placeholder titles,
  controlled `law` type, Fedlex subtitles, four metadata rows, and
  content/sections/citations/details tabs.
- HITL smoke: correction `cor_01kq7g3gxv88pag6mzsynejshk`, workflow
  `rescore-cor_01kq7g3gxv88pag6mzsynejshk`, outcome `unchanged`; metrics moved
  `applied_total 8 -> 9`, `unchanged 4 -> 5`, and `failed` stayed `4`.

Open follow-up: broaden from deterministic source snapshots to normal
source-ingestion replay for the same IDs.
