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
  adapter — so coercion bugs are in scope. Note the one thing this level still
  cannot see: Vitest transpiles with SWC and emits **no decorator metadata**, so
  `ValidationPipe` receives `metatype: undefined` and passes the raw query object
  through. Anything that depends on the DTO class surviving compilation is
  invisible here and belongs to Level 5.
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

## Level 5: Compiled-Artifact Checks (the build, not the sources)

**Purpose:** Assert properties that exist only *after* compilation, against the
artifact production actually runs.

**What it catches:**

- Decorator metadata that the TypeScript emit drops — the class of bug where a
  test suite and the built app disagree about what the code even means

**Why it is not optional.** #728: `norm-hierarchy.controller.ts` imported its
query DTO with `import type`. That erases the class, so `design:paramtypes`
carried `Function` instead of the DTO, `ValidationPipe` had nothing to
instantiate, and with `whitelist: true` it handed the handler an **empty
object** — silently dropping every query parameter. `in_force_at`, ADR-0033 §2's
temporal-validity differentiator, did nothing at all in production while the
endpoint kept returning a well-formed, plausible answer to a different question.

Every other level reported green, and correctly so: under Vitest no decorator
metadata is emitted at all, so `ValidationPipe` passes the raw query through and
the parameters flow. The tests were not wrong; they were **structurally
incapable** of observing the defect. That is ADR-0040's concern exactly — a gate
reporting green over work it never did — and no amount of additional
source-level testing closes it.

**Where it lives:**

| Surface | Check | Runner |
|---|---|---|
| `legal-search/api` | `scripts/check-validation-metadata.mjs` — every whole-object `@Query()`/`@Body()`/`@Param()` binding in `dist/**/*.controller.js` resolves to a real DTO class | `npm run test:compiled` (invoked by `npm run check`) |

**Rules:**

- Load the **built artifact**. A check that reads `src/` is a Level 1 test
  wearing this level's name, and inherits the blindness it exists to remove.
- Prefer a check that catches the **class** of defect over one keyed to its
  syntax. `check-validation-metadata.mjs` asserts the metatype is a real class,
  so an interface, a type alias, a barrel re-export, or any future erasing
  construct fails too — not just `import type`.
- Pair it with removing the reintroduction vector where one exists. Biome's
  `style/useImportType` autofix rewrote the corrected value import straight back
  to `import type` on every `npm run format`, so the rule is **off for
  `*.controller.ts`** in `legal-search/api/biome.json`. Per-file `biome-ignore`
  comments were the previous defence and they failed: the fix depended on every
  future author knowing to add one.
- **Give the guard its own test.** A guard that never fires looks exactly like a
  passing one — see `src/core/validation/validation-metadata-guard.spec.ts`,
  which drives the detector with the erased shapes observed in `dist/`.

**Expected frequency:** Run on every commit (part of the per-surface gate).

**Required in MVP:** Yes, for any surface whose runtime behaviour depends on
decorator metadata.
