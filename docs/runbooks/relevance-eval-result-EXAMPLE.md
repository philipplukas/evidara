# Example: relevance eval result (replace with real staging data)

Owner: Legal-search / platform  
Last reviewed: 2026-04-09  
Last verified: 2026-04-09  
Applies to: **TAR-82**, **TAR-68** (illustration only; not a locked baseline)

**Do not treat this file as a locked baseline.** Copy the table into Linear **TAR-82** / **TAR-68** after running queries against **your** staging corpus. See [relevance-eval-result-template.md](relevance-eval-result-template.md).

## Run metadata

- **Environment:** `https://legal-search.example.invalid` (replace)
- **Corpus snapshot / date:** 2026-04-09
- **Ranking / boost version:** `main` @ `abc1234` (replace)
- **Runner:** local operator

| # | Query text | Top 1 `document_id` | Top 1 score | Top 2 `document_id` | Top 2 score | Top 3 `document_id` | Top 3 score | Expected doc in top 5? (Y/N) | Notes |
|---|------------|---------------------|-------------|---------------------|-------------|---------------------|-------------|------------------------------|-------|
| 1 | Bundesgericht | doc_a | 12.4 | doc_b | 11.0 | doc_c | 9.2 | Y | synthetic |
| 2 | BGE 133 III 393 | doc_x | 15.1 | doc_y | 8.0 | doc_z | 7.5 | N | replace with real expected id |

**Regression slot (if any):** none
