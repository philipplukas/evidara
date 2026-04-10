# Staging relevance pack capture (2026-04-09)

**API:** `https://legal-search-api-staging-kxc5agexna-oa.a.run.app`  
**Queries:** from [staging-relevance-query-pack-suggestions.md](../staging-relevance-query-pack-suggestions.md)

**Note:** Staging index currently returns **7** documents; **lexical ranking does not change top-3 order** across these queries (same three IDs for every row). Treat this snapshot as **infrastructure proof** (search responds); **discrimination** must be re-evaluated after a larger corpus or ranking work (TAR-82).

## Run metadata

- **Corpus size:** 7 `totalResults` for all queries below
- **Ranking / API:** staging legal-search BFF as deployed 2026-04-09
- **Scores:** not exposed on list items in this API version — column uses `n/a`

| # | Query text | Top 1 `document_id` | Top 1 score | Top 2 `document_id` | Top 2 score | Top 3 `document_id` | Top 3 score | Expected doc in top 5? | Notes |
|---|------------|---------------------|-------------|---------------------|-------------|---------------------|-------------|------------------------|-------|
| 1 | Bundesgericht | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | Same order as all rows |
| 2 | BGE 133 III 393 | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 3 | OR Art. 260 | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 4 | Mietrecht Kündigung | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 5 | Strafrecht | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 6 | Bundesgesetz über die | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 7 | BVGE | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 8 | Datenschutz DSG | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 9 | Verwaltungsgericht | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |
| 10 | Zivilprozessordnung | doc_49n3ksesast1e2gbw1b7zev9q7 | n/a | doc_7gnw34z8hfsnbqnn24c4fj6n7e | n/a | doc_61gpg0hbc0pjybgzxyavevezpt | n/a | TBD | |

**Regression slot:** none recorded (baseline not locked).
