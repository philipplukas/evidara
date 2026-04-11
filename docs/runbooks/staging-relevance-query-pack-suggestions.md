# Staging relevance — suggested query seeds (MVP)

Owner: Legal-search / platform  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: [search relevance baseline](search-relevance-baseline.md), [relevance eval result template](relevance-eval-result-template.md), Linear **TAR-82** / **TAR-68**

**Automation:** after editing your query list, run [`scripts/run-staging-relevance-query-pack.sh`](../../scripts/run-staging-relevance-query-pack.sh) (see baseline runbook).

Pick **5–10** queries for your **staging** corpus; replace or extend this list per locale and seeded content. For each query, record top-3 hits using the **template** and attach to TAR-82 (tuning) and/or TAR-68 (baseline lock).

| # | Example query (German) | Intent |
|---|------------------------|--------|
| 1 | `Bundesgericht` | Broad institutional / court name |
| 2 | `BGE 133 III 393` | Exact or near-exact citation-style token |
| 3 | `OR Art. 260` | Article + law abbreviation |
| 4 | `Mietrecht Kündigung` | Multi-term topical |
| 5 | `Strafrecht` | Short category keyword |
| 6 | `Bundesgesetz über die` | Partial statute title |
| 7 | `BVGE` | Court abbreviation |
| 8 | `Datenschutz DSG` | Acronym + domain |
| 9 | `Verwaltungsgericht` | Court type |
| 10 | `Zivilprozessordnung` | Long form law name |

**Regression rule:** after ranking changes, re-run the same pack; at most **one** agreed regression slot per release candidate (see baseline runbook).
