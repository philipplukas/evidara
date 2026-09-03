---
name: provider-temporal-semantics
description: Get `in_force_from` / `in_force_until` right when adding or reviewing an acquisition provider, so a repealed norm does not read as good law on its repeal date. Use when writing a provider that emits temporal metadata, when mapping an upstream end-date field, when reviewing a provider PR, or when a point-in-time (`in_force_at`) query returns a norm you expected it to exclude. Covers the boundary convention the repo does not have, why a passthrough test proves nothing, how to establish the upstream reading empirically, and the UTC-vs-civil-date defect next door.
---

# Temporal semantics for a new provider

The failure this prevents: **a norm repealed on 2020-06-30 answers "yes, in
force" for 2020-06-30** — or the reverse — because the producer and the consumer
disagree by one day about what `in_force_until` means, and nothing in the repo
made either of them state their reading.

This is not hypothetical and it is not one provider's bug. Issue **#843** is open
on exactly this. Read it and its comment before you touch these fields; the
comment is the correction to the body.

## 1. The convention, as it actually stands on `main`

**The consumer is inclusive** — `in_force_until` is the last day the norm *was*
in force. This is stated in four places and pinned by a test:

- `legal-search/api/src/core/norm-hierarchy/in-force.ts:25-27` — *"Last date the
  norm WAS in force — inclusive."*
- `:61` — `if (until && asOf > until) return 'repealed';` — strictly greater, so
  `asOf === until` is `in_force`.
- `:80-82` — `inForceExclusionClauses` returns exactly
  `[{ range: { in_force_until: { lt: at } } }, { range: { in_force_from: { gt: at } } }]`.
  `lt`/`gt`, used as `must_not`. There is no `lte`/`gte` anywhere in the in-force path.
- `contracts/schemas/document.schema.json`, `contracts/schemas/search-projection.schema.json`,
  and `contracts/api/legal-search.openapi.yaml` all say *"inclusive"*.
- Pinned by `in-force.spec.ts:17-21` —
  `it('treats \`in_force_until\` as the last day the norm WAS in force')`.

**The producers do not agree — with the consumer or with each other.** All four
pass the upstream end-date through with **zero days of adjustment** (no
`timedelta`, no `days=1`, anywhere):

| producer | file:line where `in_force_until` is set | upstream field | its own stated reading |
|---|---|---|---|
| `ris_ogd` | `services/ris_ogd_provider.py:370` | `Ausserkrafttretensdatum` | none stated, no in-force predicate |
| `fedlex_sparql` | `services/fedlex_sparql_provider.py:299` | `jolux:dateEndApplicability` | **inclusive** — `:48-50` "last day in force"; `:487` `in_force_until >= as_of` |
| `gemeinde_http` | `services/gemeinde_http_provider.py:282` | `ausserkrafttretendatum` | none stated, no in-force predicate |
| `lexfind_api` | `services/lexfind_api_provider.py:286` | `version_inactive_since` | **exclusive** — `:311-312` `if until is not None and moment >= until: return False` |

A fifth writer of the same field:
`document-intelligence/src/document_intelligence/normalize/xml.py:79-80` maps RIS
XML `akra` → `in_force_until`, also unadjusted.

**No ADR defines the boundary.** ADR-0033 `:122` names `in_force_at` as an anchor
tool parameter but does not define its edge. Neither `in_force_at` description in
`legal-search.openapi.yaml` states whether a norm whose `in_force_until` equals
the requested date counts.

So the convention exists on the consumer side, is contradicted by one producer,
confirmed by another, and unexamined by two. **Do not add a fifth unexamined
passthrough.**

## 2. What you must do when adding a provider

### a. Establish the upstream reading empirically, not by reading the field name

`Ausserkrafttretensdatum` and `ausserkrafttretendatum` both read *exclusive* on
their face ("date of coming-out-of-force"), and `dateEndApplicability` reads
*inclusive*. Face value is an argument, not evidence.

The probe that settles it, for any source publishing consecutive versions:

> Fetch an older version and the version that replaced it. If the older
> version's end-date **equals** the newer version's start-date, the field is
> **exclusive** (the end-date is the first day out of force). If it is the
> newer's start-date **minus one day**, the field is **inclusive**.

Where the fixtures cannot answer this, say so. Every `version_inactive_since` in
`platform-control/tests/fixtures/lexfind/search-zh-554.json` is `null` — which is
why LexFind's reading is currently recorded as *inference, not measurement*
(`tests/unit/test_lexfind_api_provider.py:222-235`).

### b. Write a test that asserts the boundary, not the passthrough

This is the trap. `tests/unit/test_ris_ogd_provider.py:140-157` feeds
`"Ausserkrafttretensdatum": "2018-12-31"` and asserts
`meta["in_force_until"] == "2018-12-31"`. It is green, it is correct, and it
proves **nothing about the semantics** — a passthrough test passes identically
under either reading.

The test that carries information is a two-sided boundary assertion, like
`tests/unit/test_lexfind_api_provider.py:239-240`:

```python
assert provider.is_in_force(record, as_of="2026-06-29") is True
assert provider.is_in_force(record, as_of="2026-06-30") is False
```

If your provider has no in-force predicate to assert against, that absence *is*
the finding — report it rather than adding a passthrough test that looks like
coverage.

### c. Document the reading in the module, next to the mapping

`fedlex_sparql_provider.py:46-52` is the pattern: name the upstream predicate,
say what it means, say when it was verified against the live endpoint, and say
that a rename is corrected *there and nowhere else*.

### d. Do not silently "fix" the convention in your provider

If your upstream field is exclusive and the consumer is inclusive, the choice
between (a) adjusting by one day at the producer and (b) redefining the field as
exclusive and changing `in-force.ts:61` to `>=` and `:81` to `lte` is a
**repo-wide decision affecting four producers and two consumers**
(`/v1/norm-hierarchy` and `/v1/coverage`). It belongs in #843 and, given it
changes a documented contract field, in an ADR — not in a provider PR. Record
what you measured, cite #843, and leave the boundary alone.

## 3. The date-arithmetic defect next door

`lexfind_api_provider.py:308` defaults `as_of` to
`datetime.now(UTC).date().isoformat()`. Force is a **civil-date** question in a
UTC+1/+2 jurisdiction, so a capture between local midnight and 01:00/02:00 lands
on the previous UTC day. The docstring at `:300-306` already says the default is
"a convenience for tests and ad-hoc inspection, not a licence to freeze the
answer into a document" — which is the right instinct and does not fix the
timezone.

Whenever you write a date for a legal question: pass the civil date explicitly,
in the jurisdiction's own timezone. A `datetime.now(UTC)` inside a temporal
predicate is a defect even when every test passes.

Related: #661's trap is why repeal must be modelled **separately from
consolidation date** (`lexfind_api_provider.py:103-113`), and #837 is why a
temporal boolean must not be frozen at capture time. `is_in_force` is three-valued
on purpose — `None` when the source publishes no start date is not `False`.

## 4. Before you claim a point-in-time query works

Two things make a green test misleading here:

- **The fields may not exist in the live index.** ADR-0048 `:257-264` records
  that `in_force_from` / `in_force_until` are among five fields **absent from the
  live `documents-000001` mapping**, so the `must_not` range clauses match
  nothing and `in_force_at` is **inert in production**. A missing field in
  OpenSearch returns empty buckets, not an error. See the
  `opensearch-mapping-drift` skill before reporting a temporal filter as working.
- **A DTO can be silently dropped by the compiled app.** #728: `/v1/norm-hierarchy`
  shipped with `in_force_at` completely inert because the controller used
  `import type`, so `emitDecoratorMetadata` wrote `Function` into
  `design:paramtypes` and `ValidationPipe` handed the handler an empty object.
  **No Vitest layer can see this.** The guards are `style/useImportType` disabled
  for `src/**/*.controller.ts` in `biome.json`, and `npm run test:compiled`
  asserting against `dist/`. Fixed at `norm-hierarchy.controller.ts:3-6`; do not
  reintroduce it, and do not accept a unit test as proof the parameter binds.

## Boundaries

- **Never adjust a date to make a test pass.** If producer and consumer disagree,
  that is #843, not a rounding error.
- **Absent is not false.** An absent `in_force_until` means "not repealed as far
  as we know", which is not "never repealed" (`in-force.ts:25-27`). An unknown-dated
  norm stays in the result set and is reported `unknown` — filtering it out would
  hide law from the agent, and silence is indistinguishable from absence
  (`in-force.ts:74-79`).
- **Do not correct #843 from inside a provider.** Report the measurement; let the
  issue own the convention.
- One stale claim to be aware of while working here:
  `tests/unit/test_lexfind_api_provider.py:233` still asserts in prose that
  "LexFind is the outlier; `ris_ogd` already emits inclusive". The #843 comment
  disputes it and the code above shows `ris_ogd` states no reading at all.

## Reference

- Issue **#843** — the open boundary defect; read the comment, not just the body
- `legal-search/api/src/core/norm-hierarchy/in-force.ts` — the consumer's convention, in one file
- `legal-search/api/src/core/norm-hierarchy/in-force.spec.ts:17-21` — the test that pins it
- `platform-control/src/platform_control/services/fedlex_sparql_provider.py:46-52` — how to document an upstream predicate
- `platform-control/tests/unit/test_lexfind_api_provider.py:213-240` — a two-sided boundary test
- [ADR-0048](../../../docs/adr/0048-completeness-crosses-the-boundary-by-projection.md) §on missing fields — why the filter is inert in production today
- `.claude/skills/opensearch-mapping-drift/SKILL.md` — whether the field your query needs is even in the index
