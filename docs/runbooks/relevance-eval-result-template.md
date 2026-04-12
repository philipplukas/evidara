# Search relevance eval result template (staging)

Owner: Legal-search / platform  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: **TAR-82**, **TAR-68**, [search relevance baseline](search-relevance-baseline.md)

Copy the table below into a **Linear comment** on TAR-82 and/or TAR-68 (or attach a spreadsheet). One row per query from the agreed **5–10 query** pack. For layout-only reference (synthetic data), see [relevance-eval-result-EXAMPLE.md](relevance-eval-result-EXAMPLE.md).

**Generate top-3 columns:** run [`scripts/run-staging-relevance-query-pack.sh`](../../scripts/run-staging-relevance-query-pack.sh) against staging (see baseline runbook **Automation hooks**), then fill **Expected doc in top 5?** and **Notes** manually.

| # | Query text | Top 1 `document_id` | Top 1 score | Top 2 `document_id` | Top 2 score | Top 3 `document_id` | Top 3 score | Expected doc in top 5? (Y/N) | Notes |
|---|------------|---------------------|-------------|---------------------|-------------|---------------------|-------------|------------------------------|-------|
| 1 |            |                     |             |                     |             |                     |             |                              |       |
| 2 |            |                     |             |                     |             |                     |             |                              |       |

## Run metadata

- **Environment:** dev or staging legal-search API base URL: `________________`
- **Corpus snapshot / date:** `________________`
- **Ranking / boost version:** (e.g. git SHA or release): `________________`
- **Runner:** `________________`

**Regression slot (if any):** Document **one** allowed regression per [search relevance baseline](search-relevance-baseline.md) release rule, or state **none**.
