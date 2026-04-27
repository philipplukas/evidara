# Internal Beta User-Flow Evidence

Owner: Platform / legal-search
Last reviewed: 2026-04-27
Last verified: 2026-04-27
Applies to: Hetzner `evidare-staging` internal beta

## Purpose

This is the canonical one-week internal beta packet while GCP billing is
disabled. It proves the smallest useful user promise:

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
- Expected result: every non-control query returns its named expected document
  in top 5.
- `q=*` must return at least one result.

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
- The expected-query pack returns each named document in top 5 for its target
  queries and `q=*` returns at least one result.
- Detail shows a non-placeholder title, controlled type, subtitle, metadata, and
  content/sections tabs.
- HITL rescore ends `changed` or `unchanged`; metrics increment the matching
  bucket.
- CNPG restore drill evidence exists, or the packet is marked blocked on backup
  proof.

## Current Evidence

2026-04-27 live check:

- Planned source-derived upgrade: Rocky PR #249 replaces the older synthetic
  corpus with the four Fedlex source-derived documents listed above and removes
  the synthetic projection rows from legal-search.
- Before marking this section verified again, Argo must sync the Rocky PR
  revision and this packet must be rerun end to end.

Open follow-up: after this source-derived corpus is live and verified, broaden
from deterministic source snapshots to normal source-ingestion replay for the
same IDs.
