# ADR-0048: Completeness crosses the boundary by projection, and never becomes a score

## Status

Proposed

## Date

2026-07-28

## Context

### The refusal ADR-0033 asked for is still not sayable

ADR-0033 §2 calls explicit coverage *"the only real cure for confident fabrication"*, and
the answer it asks for is a refusal — in its own words, *"I do not have the Hundereglement
for this commune" is a correct answer*. ADR-0042 generalised it to the sentence this ADR
uses throughout: *"I do not hold the governing norm for this question, so I will not answer
it."*

ADR-0042 built the surface — `GET /v1/coverage` — and made absence reportable rather than
inferred. But its `CoverageHolding` union has exactly two members, and `held` is a claim
about **presence**, not about **sufficiency**. So today these are the same answer:

| what we hold for `jur_ch_zh` | reported |
|---|---|
| all 1377 texts of law the canton publishes | `holding: held` |
| 4 of them (the dog-law branch, #814) | `holding: held` |

An agent deciding whether to refuse cannot tell them apart, and the two demand opposite
behaviour. Over the complete corpus, "the governing norm is not here" is a defensible
refusal. Over 4 of 1377 it is a different fabrication with the same words — *we never
fetched it* dressed as *it is not there.*

### The denominator now exists, which is what was missing

ADR-0042 §5 deferred completeness with a hard condition:

> **Completeness-within-a-scope.** We cannot say "we hold all federal animal-protection
> law." Nothing in the platform knows the denominator. Any future attempt at this must
> state the denominator's source, or it is fabrication with a percentage attached.

That condition is now satisfiable. #818 established that LexFind publishes its own per-
entity counts, and #819 persists them with provenance:

```
jur_ch_zh   expected 1377   tier published
            source  /api/frontend/v1/{lang}/entities/extended
            as_of   2026-07-28
```

`denominator_tier` is the load-bearing part: `published` (the source states its count),
`registry` (we know the units, not their contents — 2110 communes), `none` (unstatable).
A denominator without its provenance is exactly the fabrication ADR-0042 refused.

### Why this needs an ADR rather than a PR

ADR-0042 §2 states the enum rule and its escape hatch in the same breath:

> **There is no value meaning "does not exist", "no such law", or "confirmed absent", and
> none will be added.** If a future requirement seems to need one, that is a requirement
> to revisit this ADR, not to extend the enum.

And §4 draws the ownership boundary this change crosses. This ADR is that revisit — and it
is the revisit ADR-0042 explicitly anticipated, naming this exact scope in its §5:

> Surfacing `expected` in legal-search's `/v1/coverage` — which would be the first fact
> there whose `basis` is not `index` — remains deferred and would revisit this ADR.

Both ADRs are `Proposed`. This one builds on ADR-0042's rules as written; if ADR-0042
changes before acceptance, the two must be reconciled rather than read independently.

## Decision

### 1. `holding` is not extended. Completeness is a separate, orthogonal claim

`CoverageHolding` stays exactly `held | not_held`.

ADR-0042 kept it two-valued so that no caller could find a value meaning *confirmed absent
in law*. Adding a third member — `held_complete`, or worse `not_held_confirmed` — would
put presence and sufficiency on one axis and re-open precisely that door.

They are different questions and get different fields:

```
holding: held | not_held           does the index contain matching documents?
completeness: { … } | absent       how much of what exists do we hold?
```

A group may be `held` with no completeness block at all. That is the common case and it is
honest: we hold something, and we cannot say what fraction.

### 2. The denominator crosses the boundary by **projection**, not by pull

ADR-0042 §4 rejected two mechanisms, and both are **pull**:

> **Call platform-control at request time.** … a runtime dependency on the read path …
> **Bake a snapshot at build time.** … Run history changes constantly. A baked snapshot
> would make the endpoint state a freshness claim that is itself stale — an endpoint that
> lies.

Both rejections stand. Neither applies to **push**, which is how facts reach legal-search's
index at all: `document-intelligence` publishes `document.processed`, `projection-bridge`
routes it, and legal-search applies it. Nothing about that is a runtime dependency, and
nothing about it is stale by construction — it updates when the underlying fact updates.

The precedent is narrower than it looks, and saying so is the point:

- That push path is **document-intelligence → NATS → projection-bridge → legal-search**,
  and `projection-bridge` is a *document-intelligence* job.
- **No platform-control-produced event reaches legal-search today.**
  `contracts/manifest.yaml` records platform-control as producer of exactly one event —
  `artifact_bundle.available`, consumed by document-intelligence. The one candidate that
  would close the gap, `index_update.requested`, carries `"No deployed v1 emitters exist"`
  in its own schema and is not in the manifest.
- The single platform-control fact legal-search consumes today is the **jurisdiction
  tree**, and it arrives by **build-time export**
  (`contracts/vocabularies/jurisdiction-hierarchy.json`) — which is precisely the ADR-0004
  precedent ADR-0042 §4 leaned on when it rejected a baked snapshot for coverage.
- `structurizr/workspace.dsl` already draws a platform-control → broker → legal-search
  edge. That edge is aspirational; this ADR is what would make it real.

So this ADR does not ride an existing edge — it **establishes the first one**. That is a
larger commitment than reusing a path, and it is stated here rather than assumed:
platform-control publishes a coverage event when a reconciliation is recorded; legal-search
stores the denominator alongside its own counts and serves both.

It remains true that this is not a loophole in §4 — push is the option §4 did not
enumerate, and it is the only one with neither of the failure modes §4 named. But the
argument rests on push being *sound*, not on it being *already there*.

**Availability consequence, stated plainly:** if the projection path stops, the denominator
goes stale rather than absent. §5 below is how that is prevented from lying.

### 3. The response carries **two bases**, and says which is which

`CorpusCoverageView.basis` is `"index"` today and stays that way — the counts are still
derived solely from what we hold. The completeness block carries its own:

```jsonc
{
  "basis": "index",                       // the numerator
  "groups": [{
    "key": "jur_ch_zh",
    "documents": 1377,
    "holding": "held",
    "completeness": {
      "basis": "platform_control_runs",   // the denominator — a DIFFERENT provenance
      "expected": 1377,
      "denominator_tier": "published",
      "denominator_source": "/api/frontend/v1/{lang}/entities/extended",
      "denominator_as_of": "2026-07-28T12:04:31Z"
    }
  }]
}
```

One response, two provenances, neither disguised as the other. A reader who trusts the
index count and distrusts the acquisition figure can act on that; collapsing them into one
number would remove the choice.

### 4. No percentage, ratio, or score. Still

ADR-0042 rejected these outright:

> **Report a coverage percentage or a completeness score.** Rejected outright … A
> completeness score would be the single most dangerous field we could ship here.

Unchanged, and now enforced rather than asked for: `expected` and `documents` are both
present, and a caller that wants a ratio computes it and owns it. The API ships neither.

`test_coverage_never_publishes_a_completeness_score` already guards the platform-control
side; the legal-search side gets the same gate.

### 5. A stale or missing denominator degrades to **absent**, never to a number

Three rules, each a test:

- **No projected denominator → no `completeness` block.** Not `expected: null`, not
  `expected: 0`. The field is absent, and a caller that requires it must handle its
  absence rather than read a zero. Note this **deliberately diverges** from the
  platform-control shape it mirrors, where `expected: null` is the sanctioned
  representation (`schemas/coverage.py:29-30`). The ledger is an operator surface where a
  null column is read by a human; this is an agent-facing read path where a nullable field
  is one `or 0` away from #818's fabricated-completeness defect. The divergence is stated
  so a future reader does not file one half as a bug against the other.
- **`denominator_tier: registry` may not support a completeness claim.** It counts units
  (2110 communes), not documents; the comparison is a category error. Breadth only.
- **A denominator older than a staleness horizon is served with `denominator_as_of`
  unchanged and no derived judgement.** The API reports when the fact was true and refuses
  to decide whether that is recent enough — the caller's question, not ours. This follows
  ADR-0042 §3's naming discipline: `last_processed_at` is *"exactly as strong as its
  name."*

### 6. What this makes sayable, and what it does not

Sayable: *"I hold all 1377 texts of law Zürich publishes, and the governing norm for this
question is not among them — so I will not answer."*

Still **not** sayable, and never will be from this endpoint: *"the norm does not exist."*
ADR-0042's load-bearing rule is unchanged —

> **The corpus is a subset of the law by construction, and no endpoint over it can ever be
> evidence of what the law does not contain.**

Completeness raises the *quality* of the refusal. It does not convert a refusal into a
finding about the world.

## Consequences

- `contracts/events/` gains one event. `contracts/manifest.yaml` records producer and
  consumers — three pipeline event schemas in `contracts/events/` already lack manifest
  entries (`document-withdrawn`, `index-update-requested`, `raw-artifact-available`), and
  this one will not. It would be the manifest's first event with producer
  `platform-control` and consumer `legal-search`.
- legal-search gains a store for projected denominators. It gains **no** platform-control
  client, no config pointing at it, and no runtime dependency: the ADR-0004 precedent and
  §4's boundary are intact.
- `/v1/coverage` is still unlocked in `contracts/manifest.yaml` (*"lock it once an MCP tool
  depends on it"*), so this shape can move before it is depended upon. It should be locked
  at the same moment ADR-0033 step 6 wires a tool to it, not before.
- The admin ledger (#819) and this endpoint now report the same denominator from two
  sides. They will disagree while a projection is in flight. That is a visible,
  explainable lag, not a contradiction — and `denominator_as_of` is how a reader sees it.
- `structurizr/workspace.dsl` gains the coverage projection edge, and this is a real
  change rather than a relabel. `platformControl -> broker` exists; `broker -> legalSearch`
  is today satisfied only via the document-intelligence-owned `projection-bridge`. A
  coverage projection consumed by legal-search needs either a new consumer component or an
  honest relabel of that edge — see Decision §2.

## Alternatives considered

**Add a third `holding` value.** Rejected. It puts presence and sufficiency on one axis,
and the reason ADR-0042 fixed the enum at two members was to keep any value from drifting
toward *confirmed absent in law*. `held_complete` invites `not_held_confirmed` next.

**Compute completeness in legal-search from `source_version_id` cardinality.** Rejected —
it is a denominator invented from the numerator. Counting the source versions we ingested
says nothing about how many exist, and it would produce a confident number with no source,
which is the exact failure §5 named.

**Have the caller join `/v1/coverage` with `/v1/acquisition-coverage` themselves.**
Rejected. It is honest but it pushes the hardest part — knowing that a `registry` tier may
not produce a ratio, that a truncated run is a sample — onto every consumer, and the first
one to get it wrong ships a percentage. The rules belong next to the data.

**Do nothing; keep completeness admin-only.** Rejected, but it is the status quo and it is
survivable. What it costs is ADR-0033's acceptance test: the dog question's *correct
refusal* is only defensible over a corpus known to be complete, and today nothing on the
read path knows that.

## Sequencing — this is designed now and built later, deliberately

Verified against `evidara-k3s` on 2026-07-28 and re-confirmed 2026-07-29 by running the
comparator itself (`npm run mapping:check-drift` against `documents-read`, exit 1): the live
`documents-000001` index carries **32 mapped fields against the canonical mapping's 37**,
and the missing five are exactly `level`, `in_force_from`, `in_force_until`, `delegates_to`,
`subordinate_to`.

That is not only the norm-hierarchy module's problem. It is `/v1/coverage`'s:

- `group_by=level` aggregates on `level.keyword`, which does not exist — so it returns
  **empty buckets, not an error**;
- `in_force_at` builds `must_not` range clauses on `in_force_from` / `in_force_until`,
  neither of which exists — so the clauses match nothing and the filter is **inert**.

One of the endpoint's four `group_by` dimensions (`level` — the others, `jurisdiction`,
`authority` and `document_type`, are mapped), its entire temporal filter, and the
`no_repeal_date` sub-aggregation are dead in production, silently, for the reason AGENTS.md
already records twice (#675, #713, #728): *"because OpenSearch returns empty buckets rather
than an error for a missing field, both presented as query bugs for months."*

Worth stating exactly, because it is a gap rather than a contradiction: ADR-0042 §6's live
verification caught a *dynamically-mapped text* field, which throws — and the 503 guard in
`opensearch.adapter.ts` matches on that throw. An **absent** field throws nothing, so the
guard cannot see this class at all.

Building completeness onto that surface would add a field an operator could trust to an
endpoint several of whose existing answers are hollow. So this ADR is **Proposed and
unimplemented on purpose**.

The prerequisite is larger than "a reindex", and the distinction matters enough to state:

- **The mapping is one problem.** `scripts/opensearch-alias-cutover.ts` fixes it — a new
  index created from the canonical mapping, then an atomic alias swap.
- **The documents are a second one.** All five fields are also absent from `_source` on all
  six live documents, not merely unmapped. They are stale projections, written before
  `projections.service.ts:257-265` derived `level` / `subordinate_to` / `in_force_from`.
  Reindexing them yields a correct mapping over documents that still carry no values, so
  `group_by=level` would return empty buckets *for a second reason* and look identical.
  They must be **re-projected**, which is the `--stage-write` → Delta backfill →
  `--promote-read` path, not `--reindex`.
- **`delegates_to` is a third case** and is not fixed by either: `projections.repository.ts:111`
  marks it *"declared, not yet produced."* Nothing emits it yet.

Anyone who reindexes, re-runs the comparator, sees green, and concludes the feature works
will have fixed the measurement and not the thing measured.

The wider point this ADR inherits: nothing ran the drift comparator against production. The
comparator existed, the canonical mapping existed, the discipline was written down — and five
fields still drifted unnoticed, silently, for months. A gate that never runs is the same as no
gate. That specific gap is now closed by a scheduled workflow; the reindex and re-projection
it reports on are still owed.

## Related

- ADR-0042 — the split this revisits (§2 the enum, §4 the boundary, §5 the deferral)
- ADR-0033 §2 — coverage as the cure for confident fabrication
- ADR-0004 — contracts at the root; build-time export precedent
- ADR-0030 — acceptance evidence, and the two-key lock
- #816 the ledger, #818 enumeration, #819 the platform-control half, #709 the original
  coverage endpoint
