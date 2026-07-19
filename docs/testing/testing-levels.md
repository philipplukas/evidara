# Testing Levels

## Level 3: Contract Tests

**Purpose:** Validate schemas and event contracts at component boundaries.

**What it catches:**

- Schema violations in API payloads, events, and stored data
- Breaking contract changes between components
- Missing required fields and invalid enum values

**Expected frequency:** Run on every commit.

**Required in MVP:** Yes. Schema validation for core contracts (`ArtifactBundleManifest`, `Document`, `Section`, `ProcessingManifest`, events) is required from day one.

## Level 4: Backend Integration Tests (real datastore)

**Purpose:** Validate that the query a component builds actually matches the
data the datastore holds — the value and mapping *conventions* that no mocked
test can see.

**What it catches:**

- Case conventions (`CH` vs `ch` against a case-sensitive `keyword` field)
- Type coercion at the HTTP boundary (the string `"false"` is truthy)
- Mapping drift (aggregating a `.keyword` sub-field the index does not have —
  OpenSearch returns empty buckets rather than erroring)

**Why it is not optional.** #672, #673 and #675 were three separate instances of
this class, and all three shipped through a fully green suite. Every layer was
individually correct and unit-tested; they were only wrong *jointly*, against a
real index. The frontend e2e/VRT suite mocks the search API (`mockSearchApi`),
so nothing in the repo had ever met a real mapping or a real value convention.

**Where it lives:**

| Surface | Harness | Runner |
|---|---|---|
| `legal-search/api` | Testcontainers OpenSearch | `npm run test:integration` (invoked by `npm run check`) |
| `platform-control` | Testcontainers Postgres | `uv run pytest` |

**Rules:**

- Assert on **observable behaviour** (result counts, facet buckets), never on
  the shape of the query body. A test that asserts the query body is just the
  bug written twice.
- Drive the **full boundary** — validation pipe, DTO, controller, service,
  adapter — so coercion bugs are in scope.
- Seed a corpus that mirrors the **real value conventions** (uppercase ISO
  codes, lowercase languages, a mix of boolean flags). The conventions are the
  thing under test.
- Seed from the **in-repo source of truth**, and assert behaviour against that
  shape only. Where a deployed schema is known to differ, do **not** also run
  the behavioural suite against the drifted shape: that makes the drift a
  supported configuration, and satisfying both shapes forces the queries down to
  a lowest common denominator. It is how #675 was first "fixed" — by aggregating
  on bare field names to match a drifted index, which then fails against the
  GCP-provisioned index where those fields are dynamic `text`.
  Drift belongs in a **drift check**, not in a behavioural test: see
  `legal-search/api/src/core/opensearch/mapping-drift.ts`, its
  `mapping-drift.integration.spec.ts` (asserts the real bootstrap path produces
  a drift-free index, and that the detector flags the drifted shape), and
  `npm run mapping:check-drift` for pointing the same comparison at a live
  cluster.
- Pin conventions that no behavioural test can see. Under the canonical mapping
  both `jurisdiction` and `jurisdiction.keyword` aggregate correctly, so only a
  structural assertion distinguishes them — `facet-fields.spec.ts`.
- **No skip-when-Docker-is-missing escape hatch.** A silently skipped
  integration test reproduces the exact failure mode this level exists to
  prevent.

**Expected frequency:** Run on every commit (part of the per-surface gate).

**Required in MVP:** Yes.
