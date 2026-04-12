# Search relevance baseline (MVP)

Owner: Legal-search / platform  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: **dev** (default remote corpus for dev-first teams), **staging** when operated, **prod**

This runbook defines how we **tune and regress** search relevance without changing API contracts. It pairs Linear **TAR-82** (relevance tuning) and **TAR-68** (locked baselines).

## Indexed fields used for lexical rank

OpenSearch `multi_match` (see `legal-search/api/src/modules/search/opensearch.adapter.ts`) weights:

| Field             | Boost | Notes                                      |
|-------------------|------:|--------------------------------------------|
| `title`           | 4     | Primary user trust signal                  |
| `structural_path` | 2     | Breadcrumb / hierarchy matches             |
| `regeste`         | 2     | Decision summaries (seed / legacy corpora) |
| `content`         | 1     | Full text when present on projection       |
| `content_preview` | 1     | DI / projection preview                    |
| `docket_number`   | 2     | Decision identifiers                       |

Changing boosts is a **pipeline-change** / **user-visible-behavior** decision: capture before/after evidence when adjusting.

## Agreed eval pack (remote)

Run against a **deployed** legal-search API (**dev** Cloud Run when you have no staging GCP project; **staging** or **prod** when those exist) with a fixed corpus snapshot:

1. Pick **5–10 queries** representative of MVP operator demos (exact titles, partial titles, article numbers, court abbreviations).
2. For each query, record: top **3** `document_id` values, `relevance_score`, and whether the expected doc appears in top **5**.
3. Store results in the release checkpoint (spreadsheet or Linear issue comment) and link from the weekly readiness note.

**Regression expectation:** after ranking changes, re-run the pack; **no more than one** agreed “allowed regression” slot per release candidate (document explicitly in the checkpoint).

## Automation hooks

- **API smoke:** `evidara workflow mvp-acceptance` (when configured for **dev** or staging URLs) exercises the locked MVP path; extend evidence with manual top-N checks from the table above when tuning relevance.
- **Query pack:** from repo root, with `EVIDARA_LEGAL_SEARCH_URL` and `EVIDARA_LEGAL_SEARCH_TOKEN` set (same Bearer pattern as [GCP local Cloud Run auth](../setup/gcp-local-cloud-run-auth.md)), run [`scripts/run-staging-relevance-query-pack.sh`](../../scripts/run-staging-relevance-query-pack.sh) (works for any environment URL). It reads one query per line (see [`scripts/fixtures/staging-relevance-queries.example.txt`](../../scripts/fixtures/staging-relevance-queries.example.txt)), calls `GET /v1/search`, and prints a Markdown table — paste into [relevance-eval-result-template.md](relevance-eval-result-template.md) and attach to **TAR-82** / **TAR-68**.
- **CI:** unit tests cover projection + mapper behavior; full relevance requires OpenSearch integration (Testcontainers) or a **deployed** index — do not block PRs on remote-only numbers.

## Related docs

- [First vertical slice exit gates](first-vertical-slice-exit-gates.md) — Gate C / search expectations  
- [MVP acceptance scenario pack](mvp-acceptance-scenario-pack.md) — end-to-end operator checks  
