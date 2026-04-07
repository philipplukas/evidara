# Legal Search Testing

## Scope

Testing strategy for the legal-search component, which owns:

- Projection building (canonical → search-ready)
- Indexing into OpenSearch
- Search APIs (search, filters, pagination)
- Document detail APIs
- Query behavior and relevance
- Frontend search flow
- Frontend detail page rendering

---

## Minimal Tests for MVP — Backend / Serving

### Unit Tests

#### Projection builder

- Canonical document → search projection produces expected fields
- Missing optional fields are handled gracefully (null, default)
- Projection includes required fields: `document_id`, `title`, `jurisdiction`, `document_type`, `sections`

#### Query builder

- Search query string → OpenSearch query DSL is correct
- Jurisdiction filter → proper filter clause
- Multi-filter requests (jurisdictions, languages, document types, refinements) map to expected bool filters
- Empty query → returns sensible default (e.g., match_all with sort)
- Special characters in query are escaped or handled

### Contract Tests

- Search API response conforms to API schema
- Detail API response conforms to API schema
- Pagination metadata is present and correct
- Error responses follow standard error schema

### OpenSearch Mapping Validation

- Index mapping is valid and can be applied
- Required fields are mapped with expected types (keyword, text, date)
- Analyzer configuration is correct for legal content (language analyzers, etc.)

### Indexing Smoke Test

Use a tiny sample dataset (3–5 documents):

1. Build projections from golden canonical documents
2. Index them into a test OpenSearch instance
3. Verify all documents are indexed (count match)
4. Run each search smoke query (see below)
5. Verify detail endpoint returns full content

### Indexing Parity Check

Compare canonical documents eligible for indexing against documents actually indexed:

- Count of canonical docs eligible == count of indexed docs
- If mismatch, identify which documents are missing

### Search Quality Smoke Tests

Maintain 3–5 known queries with expected results:

| Query Type | Example Query | Assertion |
|-----------|---------------|-----------|
| Exact title query | `"Obligationenrecht"` | Expected doc appears in top 5 |
| Keyword query | `Vertragsverletzung` | Hit count > 0 |
| Jurisdiction filter | `jurisdiction: CH-OR` | Expected doc in results, results only contain CH-OR |
| Section keyword | `Gewährleistung` | Hit count > 0, result has matching section snippet |
| Citation query (later) | `Art. 97 OR` | Expected doc appears (add when citation search is supported) |

**Assertions should remain simple:**

- Expected document appears in top N results
- Hit count > 0
- Expected facet/filter value is present in response
- No errors returned

---

## Minimal Tests for MVP — Frontend

### Render Tests

- **Search page render test:** search page renders without crashing, search input is visible
- **Document detail page render test:** detail page renders without crashing, title and sections are visible

### User Flow Test

One end-to-end user flow:

1. Search query is entered in the search input
2. Results are displayed
3. Clicking a result opens the detail page/panel
4. Detail page shows document title and sections

### Filter Interaction Test

1. Apply a jurisdiction filter
2. Results update to show only documents matching the filter
3. Removing the filter restores full results
4. Mobile header search triggers the same search dispatch path as desktop

### Error / Empty State Test

- Empty search results show a meaningful message (not a blank page or crash)
- API error shows an error state (not an infinite spinner)

---

## Minimal Frontend Testing Strategy for a 1–3 Person Team

### Recommendations

- **A few component tests** — verify that search page and detail page render correctly with mock data
- **1–2 integration/user-flow tests** — verify the search → result → detail path works
- **Avoid large snapshot suites** — snapshots break frequently and provide low signal
- **Rely on backend contract and projection tests for most confidence** — if the API returns correct data, the frontend mostly just needs to display it

### Why this is enough

In Evidara's architecture, most correctness comes from:

- Canonical outputs (document-intelligence)
- Projection logic (legal-search backend)
- Search APIs (legal-search backend)

The frontend is a thin layer over well-validated APIs. A handful of behavior tests provides real confidence without a maintenance burden.

### What NOT to do early

- Do not build lots of snapshot tests
- Do not invest in visual regression testing
- Do not test across a large browser matrix
- Do not write very brittle DOM-detail assertions (avoid testing specific CSS classes or pixel positions)
- Do not build a Storybook or component library testing suite yet

---

## Drift Checks

| Check | What it catches |
|-------|----------------|
| Search results empty when indexed docs exist | Indexing or query broke |
| Detail page missing essential fields | Projection dropped fields |
| Filters stop returning expected results | Filter logic or mapping changed |
| Section snippets disappear unexpectedly | Snippet generation or section indexing broke |

---

## Confidence Goal

These tests should answer:

- **Can users find the right document?** — Search smoke tests, query tests, and the user flow test prove this.
- **Does legal-search remain a faithful serving projection of canonical data?** — Parity checks and projection unit tests prove this.

---

## Later Expansion

| Phase | Addition |
|-------|---------|
| Post-MVP | Search relevance benchmarks (nDCG, precision@k) |
| Post-MVP | Pagination and sorting tests |
| Post-MVP | Frontend accessibility tests |
| Later | Performance / load testing for search |
| Later | Multi-language search quality tests |
| Later | Mobile / responsive layout tests |
