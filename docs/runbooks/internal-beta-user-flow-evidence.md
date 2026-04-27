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
| `doc_2adgt1ejqzhjj24tn8svn54h08` | Rocky GitOps `evidara-di-seed` | Searchable title `Evidara staging seed document`, `type=law`, Fedlex subtitle, detail metadata, two sections |
| `doc_76v36gavcnq3sfs52fbsbvzs81` | Rocky GitOps `evidara-di-seed` | Searchable title `Swiss Code of Obligations staging excerpt`, `type=law`, Fedlex subtitle, useful metadata |
| `doc_2dg03eb27dws3g13j19t1f94ax` | Rocky GitOps `evidara-di-seed` | Searchable title `Federal Supreme Court staging decision on contract notice`, `type=decision`, Bundesgericht subtitle, useful metadata |
| `doc_6qkdbsn4jan80qg7fs09qj7dc5` | Rocky GitOps `evidara-di-seed` | Searchable title `Staging commentary on proportionality and notice periods`, `type=commentary`, commentary subtitle, useful metadata |

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
   from deltalake import DeltaTable
   for name in ["published_documents", "published_sections", "processing_manifests"]:
       table = DeltaTable(f"file:///var/lib/evidara/surfaces/{name}").to_pyarrow_table()
       print(f"{name}: {table.num_rows} rows")
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
   curl -fsS http://127.0.0.1:18080/v1/documents/doc_2adgt1ejqzhjj24tn8svn54h08 |
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

- `q=*`: `totalResults=1`
- seeded document title: `Evidara staging seed document`
- seeded document type: `law`
- detail metadata: `Dokumenttyp`, `Behorde`, `Zustandigkeit`, `Sprache`
- tabs: `Inhalt`, `Abschnitte`, `Details`

Open follow-up: expand from one deterministic seed document to a 3-5 document
trusted beta corpus before making broader relevance claims. Rocky PR #246 moves
that follow-up from plan to implementation; rerun this packet after Argo sync to
replace the one-document live evidence above.
