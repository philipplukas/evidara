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
is intentionally small and deterministic, but broad enough to test several
research intents beyond the original four-document control set.

## Beta Corpus

Corpus version: `internal-beta-v2`

| Document ID | Source | Expected user-facing evidence |
| --- | --- | --- |
| `doc_6vfta1cd5xy642g7eb59j8wkfm` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 101 snapshot; searchable title `Federal Constitution of the Swiss Confederation`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_67b9202dsxm52sa36dsfvcm6bt` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 220 snapshot; searchable title `Code of Obligations`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_20djzpnf2yytwg9k74zyzjdeta` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 272 snapshot; searchable title `Civil Procedure Code`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_2em3ky37mw9tm7hxh5nkw0zkh7` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 235.1 snapshot; searchable title `Federal Act on Data Protection`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_2adkyv1qccx2pg3mqa7d233s0y` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 210 snapshot; searchable title `Swiss Civil Code`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_30hr7xpm9ptmmanpbydwpxdv61` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 311.0 snapshot; searchable title `Swiss Criminal Code`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_4n4nh4khmzfxh3hdshpvw6x4mp` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 312.0 snapshot; searchable title `Criminal Procedure Code`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_6mej0nyg3qfenw0zbdmhtq6cmn` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 281.1 snapshot; searchable title `Debt Enforcement and Bankruptcy Act`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_4pqxtsmegg44t5zg3es8d27b4v` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 172.021 snapshot; searchable title `Federal Act on Administrative Procedure`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_1f0vr4pdkn9havmnws60mb9n6y` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 173.110 snapshot; searchable title `Federal Supreme Court Act`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_3vyh663grb4kwyb96x4sd8xb1f` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 291 snapshot; searchable title `Federal Act on Private International Law`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_1jyt8vad5ed2p294t31ctj53dw` | Rocky GitOps `evidara-di-seed` | Source-derived Fedlex SR 251 snapshot; searchable title `Cartel Act`, `type=law`, Fedlex subtitle, useful metadata |

Query pack:

- [`scripts/fixtures/internal-beta-staging-queries.txt`](../../scripts/fixtures/internal-beta-staging-queries.txt)
- [`scripts/fixtures/internal-beta-staging-expected.tsv`](../../scripts/fixtures/internal-beta-staging-expected.tsv)
- [`scripts/fixtures/internal-beta-staging-documents.tsv`](../../scripts/fixtures/internal-beta-staging-documents.tsv)
- [`scripts/fixtures/internal-beta-staging-withdrawn-documents.txt`](../../scripts/fixtures/internal-beta-staging-withdrawn-documents.txt)
- Expected result: the beta queries return their named source-derived
  document(s) in top 5. The original four rows remain the control set. Broad
  source-health rows may assert non-empty results instead of fixed ranking.
- `q=*` is the corpus-health control. It must return `totalResults=12`, and the
  visible document set must be exactly the 12 source-derived Fedlex documents
  listed above.
- The old synthetic beta document IDs are tombstones: detail reads must return
  `404` from legal-search.
- Detail reads for all source-derived documents must show a
  non-placeholder title, controlled `law` type, Fedlex subtitle, at least four
  metadata rows, and `content`, `sections`, `citations`, and `details` tabs.

This corpus is enough for the internal beta trust loop and first relevance
breadth check. It is not evidence that broad legal relevance is solved.

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

6. Verify normal replay evidence after staging is configured with
   `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=local_outbox`:

   ```bash
   kubectl -n evidare-staging port-forward svc/platform-control-api 18079:8080
   kubectl -n evidare-staging port-forward svc/legal-search-api 18080:8080
   export EVIDARA_PLATFORM_CONTROL_URL=http://127.0.0.1:18079
   export EVIDARA_LEGAL_SEARCH_URL=http://127.0.0.1:18080
   export EVIDARA_REPLAY_COMMAND='kubectl -n evidare-staging exec deploy/document-intelligence-consumer -- document_intelligence_replay_local_outbox --outbox-dir /var/lib/evidara/raw-artifacts/event-outbox --legal-search-api-url http://legal-search-api:8080 --keep-projections'
   export EVIDARA_REPLAY_WITHDRAW_COMMAND='kubectl -n evidare-staging exec deploy/document-intelligence-consumer -- document_intelligence_replay_local_outbox --outbox-dir /var/lib/evidara/raw-artifacts/event-outbox --legal-search-api-url http://legal-search-api:8080 --withdraw-only'
   ./scripts/prove-internal-beta-normal-replay.sh
   ```

   This creates normal platform-control runs for the 12 Fedlex targets, replays
   local outbox `artifact_bundle.available` events through DI, verifies applied
   legal-search projection history for each run, withdraws the replay
   projections, then reruns the exact seeded-corpus query gate. Do not leave
   replay projections visible unless collecting screenshots intentionally.

7. Verify the source-derived expansion replay pack:

   ```bash
   export INTERNAL_BETA_REPLAY_TARGETS_FILE=scripts/fixtures/internal-beta-expansion-normal-replay-targets.tsv
   export EVIDARA_REPLAY_REQUIRE_SOURCE_TITLES=1
   ./scripts/prove-internal-beta-normal-replay.sh
   ```

   The expansion pack intentionally uses `fedlex_sparql` targets, not raw
   `www.fedlex.admin.ch` pages. The raw public pages are SPA shells and are
   only useful for plumbing checks; the SPARQL route carries source-derived
   titles and expression metadata. Acceptance requires replay records for every
   expansion target, source URLs matching the Fedlex work URI, non-`Fedlex`
   document titles matching the expected statute title, projection withdrawal,
   and the canonical seeded query gate still passing afterward.

## Acceptance

- `rocky-agents-staging` is `Synced` and `Healthy`.
- `evidara-di-seed` is complete and Delta surfaces are readable.
- The expected-query pack returns each named source-derived document in top 5,
  and `q=*` returns exactly the 12-document beta corpus.
- Old synthetic document IDs return `404` from legal-search detail.
- Detail shows a non-placeholder title, controlled `law` type, Fedlex subtitle,
  at least four metadata rows, and content/sections/citations/details tabs.
- HITL rescore ends `changed` or `unchanged`; metrics increment the matching
  bucket.
- CNPG restore drill evidence exists, or the packet is marked blocked on backup
  proof.
- Normal replay proof creates outbox events for the same 12 targets, applies
  temporary projections, withdraws them, and leaves `q=* totalResults=12`.
- Expansion replay proof creates source-derived Fedlex SPARQL projections beyond
  the canonical 12, validates source/title evidence, withdraws them, and leaves
  `q=* totalResults=12`.

## Current Evidence

2026-04-27 live check after `internal-beta-v2` rollout:

- Argo: `Synced Healthy Succeeded` at
  `6b0fff06bfc152eaf8872cb79fef82189a7bdacc`.
- `evidara-di-seed`: complete, `corpus_version=internal-beta-v2`,
  `corpus_size=12`, legacy synthetic withdrawals remain not indexed.
- Delta rows: `published_documents=16`, `published_sections=32`,
  `processing_manifests=16`. The extra four rows are preserved historical DI
  surface rows from the pre-source-derived seed; legal-search visibility is
  controlled by withdrawal events and the v2 projection set.
- Query gate: [`scripts/check-internal-beta-query-pack.sh`](../../scripts/check-internal-beta-query-pack.sh)
  passed; `q=*` returned exactly the 12 source-derived documents.
- Legacy synthetic details: old document IDs return `404` from legal-search.
- Detail trust: all 12 source-derived documents have non-placeholder titles,
  controlled `law` type, Fedlex subtitles, four metadata rows, and
  content/sections/citations/details tabs.
- HITL smoke: correction `cor_01kq7wyp4h2t2m31gsgfe9m44d`, workflow
  `rescore-cor_01kq7wyp4h2t2m31gsgfe9m44d`, outcome `unchanged`; metrics moved
  `applied_total 10 -> 11`, `unchanged 6 -> 7`, and `failed` stayed `4`.

Open follow-up: promote the SPARQL expansion pack into the next seeded corpus
only after the replay evidence shows acceptable title, source, and projection
quality.
