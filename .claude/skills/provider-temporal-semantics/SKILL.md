---
name: provider-temporal-semantics
description: Get `in_force_from` / `in_force_until` right when adding or reviewing an acquisition provider, so a repealed norm does not read as good law on its repeal date. Use when writing a provider that emits temporal metadata, when mapping an upstream end-date field, when reviewing a provider PR, or when a point-in-time (`in_force_at`) query returns a norm you expected it to exclude. Covers why the field name is not evidence, why a passthrough test proves nothing, the probe that establishes an upstream reading, and the UTC-vs-civil-date defect that is still open.
---

# Temporal semantics for a new provider

The failure this prevents: **a norm repealed on 2020-06-30 answers "yes, in
force" for 2020-06-30** — because the producer and the consumer disagree by one
day about what `in_force_until` means.

There is a second, worse failure this skill exists to prevent, and it nearly
happened: **converting a producer that was already correct.** Read §2 before you
touch a date.

## 1. The one rule

> **The field name is not evidence. A passthrough test is not evidence.
> Only a comparison against real consecutive versions is.**

Everything below is that rule, worked.

## 2. The inference that was plausible, and wrong

`Ausserkrafttretensdatum` — "date of ceasing to be in force" — reads **exclusive**
on its face. So does `ausserkrafttretendatum`. Issue #843's comment reasoned from
exactly that, and inferred the four producers were probably all exclusive and the
consumer was the odd one out.

Measured against the live portals, **RIS is inclusive**: B-VG Art. 11 ends
`2024-04-30` and its successor starts `2024-05-01`; Art. 15 ends `2024-02-26`,
successor `2024-02-27`. A `+1` gap, where exclusive would have made them equal.

Had anyone acted on the name-based reading and subtracted a day from RIS, Fedlex
and gemeinde, it would have **introduced** the off-by-one it was meant to remove,
in three producers, silently. The reasoning was careful and it was still wrong,
because a field name is a claim about intent and the probe is a measurement.

## 3. Where the readings actually stand

**Consumer — inclusive**, unambiguously, and pinned:

- `legal-search/api/src/core/norm-hierarchy/in-force.ts:25-27` — *"Last date the
  norm WAS in force — inclusive."*
- `:61` — `if (until && asOf > until) return 'repealed';` — strictly greater, so
  `asOf === until` is `in_force`.
- `:80-82` — `inForceExclusionClauses` returns exactly
  `[{ range: { in_force_until: { lt: at } } }, { range: { in_force_from: { gt: at } } }]`.
  `lt`/`gt`, as `must_not`. No `lte`/`gte` anywhere in the in-force path.
- Pinned by `in-force.spec.ts:17-21`; described as inclusive in
  `contracts/schemas/document.schema.json:102`,
  `contracts/schemas/search-projection.schema.json` and
  `contracts/api/legal-search.openapi.yaml`.

**Producers — measured, in open PR #859.** Read that PR rather than re-deriving
this; it carries the raw comparisons.

| producer | upstream field | reading | how established |
|---|---|---|---|
| `ris_ogd` | `Ausserkrafttretensdatum` | **inclusive** | two B-VG articles: successor start = end **+1 day** |
| `fedlex_sparql` | `jolux:dateEndApplicability` | **inclusive** | 3,000 consolidation members over 1,193 works — **1,800 of 1,806** adjacent pairs are `successor start = end + 1`; **zero** pairs equal |
| `lexfind_api` | `version_inactive_since` | **exclusive** | 27 non-null values, **26 on the 1st of a month**; Swiss repeals take effect at month starts, so a "last day in force" field would cluster on 30/31. Corroborated by `info_badge.abrogated_since` |
| `gemeinde_http` | `ausserkrafttretendatum` | **not established** | no repealed page exists to compare against. Left unconverted and labelled unmeasured — which is the correct outcome, not a gap to paper over |

**On `main` today, none of this is applied.** All four producers still pass the
upstream date through with zero adjustment (`ris_ogd_provider.py:370`,
`fedlex_sparql_provider.py:299`, `gemeinde_http_provider.py:282`,
`lexfind_api_provider.py:418`; no `timedelta` in any of them), and no ADR or
producer-side contract defines the boundary. **An open PR resolves nothing** —
check whether #859 merged before you describe the convention as settled.

Once it lands, the convention lives in `docs/architecture/boundary-contracts.md`
and in `document.schema.json`'s description. **Point at those; do not restate
them**, or this skill becomes the fifth place that can drift.

## 4. The probe

For a source that publishes consecutive versions of the same act:

> Fetch a version and the version that replaced it. Compare the older version's
> **end date** against the newer version's **start date**.
> **Equal ⟹ exclusive.** **`+1 day` ⟹ inclusive.**

Run it against more than one act. Fedlex's 1,806 pairs with six exceptions is
what a real answer looks like; two articles is enough to settle RIS only because
both agree and the alternative predicts exact equality.

### When the probe is structurally impossible — say so

It was, for LexFind. `version_inactive_since` is **null on all seven versions of
ZH 554.5, including the six inactive ones**: LexFind does not close a window on
supersession. The field is the act's *repeal* date, and only abrogations carry a
value — so there is no adjacent pair to compare, and no amount of sampling
creates one.

That is a finding, not a blocker. The reading was established from a different
signal (the month-start clustering above). **A negative result recorded honestly
is worth more than a probe reported as inconclusive**, because the next person
does not re-run it.

Note what this also means: fixtures can be silently unable to answer. Every
`version_inactive_since` in
`platform-control/tests/fixtures/lexfind/search-zh-554.json` is `null`, which is
why the repo's own boundary test still says *"This is inference, not
measurement"* (`platform-control/tests/unit/test_lexfind_api_provider.py:248`).

## 5. The test that proves nothing

`platform-control/tests/unit/test_ris_ogd_provider.py:140-156` feeds
`"Ausserkrafttretensdatum": "2018-12-31"` and asserts
`meta["in_force_until"] == "2018-12-31"`. It is green, it is correct, and it
carries **zero** information about the boundary — a passthrough test passes
identically under either reading. That is how four producers reached `main`
unexamined while looking tested.

What carries information is a two-sided boundary assertion, like
`platform-control/tests/unit/test_lexfind_api_provider.py:264-265`:

```python
assert is_in_force(version, as_of="2026-06-29") is True
assert is_in_force(version, as_of="2026-06-30") is False
```

If your provider has no in-force predicate to assert against — `ris_ogd` and
`gemeinde_http` have none — **that absence is the finding.** Report it rather
than adding a passthrough test that looks like coverage.

## 6. Still open: UTC vs the jurisdiction's civil date

`lexfind_api_provider.py:445` defaults `as_of` to
`datetime.now(UTC).date().isoformat()`. Force is a **civil-date** question in a
UTC+1/+2 jurisdiction, so a Swiss capture between local midnight and 01:00/02:00
lands on the previous UTC day and is evaluated a day early — the same one-day
class as the boundary itself. **#859 deliberately does not fix this**; it is still
open, and anyone this skill guides will hit it next.

The rule: when you write a date for a legal question, pass the civil date
explicitly, in the jurisdiction's own timezone. A `datetime.now(UTC)` inside a
temporal predicate is a defect even when every test passes. The docstring at
`:432-437` already says the "today" default is *"a convenience for tests and
ad-hoc inspection, not a licence to freeze the answer into a document"* — the
right instinct, which does not fix the timezone.

Related, and settled: #661 is why repeal must be modelled **separately from
consolidation date** (`lexfind_api_provider.py:236-245`), and #837 is why a
temporal boolean must not be frozen at capture time. `is_in_force` is
three-valued on purpose — `None` when the source publishes no start date is not
`False`.

## 7. Before you claim a point-in-time query works

Two things make a green test misleading here:

- **The fields may not exist in the live index.** ADR-0048 `:257-264` records that
  `in_force_from` / `in_force_until` are among five fields **absent from the live
  `documents-000001` mapping**, so the `must_not` range clauses match nothing and
  `in_force_at` is **inert in production**. A missing field returns empty buckets,
  not an error. See the `opensearch-mapping-drift` skill.
- **A DTO can be silently dropped by the compiled app.** #728: `/v1/norm-hierarchy`
  shipped with `in_force_at` inert because the controller used `import type`, so
  `emitDecoratorMetadata` wrote `Function` into `design:paramtypes` and
  `ValidationPipe` handed the handler an empty object. **No Vitest layer can see
  this.** Guarded by `style/useImportType` being off for `src/**/*.controller.ts`
  in `biome.json` and by `npm run test:compiled`; fixed at
  `norm-hierarchy.controller.ts:3-6`.

## Boundaries

- **Never adjust a date to make a test pass**, and never adjust one because a
  field name suggests you should. §2 is what that costs.
- **Absent is not false.** An absent `in_force_until` means "not repealed as far
  as we know", not "never repealed" (`in-force.ts:25-27`). An unknown-dated norm
  stays in the result set and is reported `unknown`; filtering it out would hide
  law, and silence is indistinguishable from absence (`in-force.ts:74-79`).
- **Do not settle the convention from inside a provider PR.** It affects four
  producers and two consumers (`/v1/norm-hierarchy`, `/v1/coverage`) and a
  documented contract field. Record what you measured and cite #843/#859.
- One stale claim still in `main` while #859 is open:
  `platform-control/tests/unit/test_lexfind_api_provider.py:259` asserts in prose
  that *"LexFind is the outlier; `ris_ogd` already emits inclusive."* The
  conclusion is right by accident — `ris_ogd` **is** inclusive — but the code
  states no reading at all, and the sentence was written as inference. Do not
  cite it as the source.

## Reference

- **PR #859** (open) — the live measurements; read it before re-deriving anything
- **Issue #843** — the boundary defect; read the comment as well as the body
- `legal-search/api/src/core/norm-hierarchy/in-force.ts` — the consumer's convention, in one file
- `legal-search/api/src/core/norm-hierarchy/in-force.spec.ts:17-21` — the test that pins it
- `platform-control/src/platform_control/services/fedlex_sparql_provider.py:46-52` — how to document an upstream predicate, with its verification date
- `platform-control/tests/unit/test_lexfind_api_provider.py:239-265` — a two-sided boundary test, and an honest "inference, not measurement" caveat
- [ADR-0048](../../../docs/adr/0048-completeness-crosses-the-boundary-by-projection.md) — why the filter is inert in production today
- `.claude/skills/opensearch-mapping-drift/SKILL.md` — whether the field your query needs is even in the index
