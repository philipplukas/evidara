# ADR-0042: Corpus coverage is an API, and it is a claim about the corpus — never about the law

## Status

Proposed

## Date

2026-07-19

## Context

### ADR-0033 §2 promises a capability that has no surface

> *"Because coverage is explicit, the agent can check whether the governing ordinance is
> actually in the corpus. If it is not, it says so and stops. Structured coverage is the
> only real cure for confident fabrication."*

Coverage is not explicit anywhere a consumer can reach. `contracts/api/legal-search.openapi.yaml`
exposes ten paths, and the only signal any of them gives about *absence* is `totalResults: 0`.

An empty result set is not a refusal. It is an ambiguity with at least four causes:

1. we do not hold the norm,
2. we hold it but the query did not match it,
3. a filter bug dropped it (#672 did exactly this — every deep-linked search returned zero),
4. the norm does not exist in the world.

Cause 4 is the one nobody can distinguish from causes 1–3, and it is the only one that would
license an agent to answer *"no law prohibits this."* Today a caller cannot tell them apart at
all, so any agent built on this API must either treat every empty result as a refusal (useless)
or guess (dangerous).

### The measured failure — M13 iteration 2, #628

Against the live index (73 documents, all CH federal):

```
q=Hund           -> 0 results     q=Hundegesetz -> 0
q=Hundereglement -> 0             q=Tierschutzverordnung -> 0
control: q=Bundesverfassung -> 2 · q=Schuldbetreibung -> 1 · q=Grundrechte -> 2
```

The dog queries returned zero and the controls returned hits, so the emptiness was genuine
absence rather than #672. The acceptance question was scored a **qualified pass** on that basis.

**The adjacent query is where it broke.** `q=Tierschutz` returned **2 results, the
Bundesverfassung first** — BV Art. 80 mentions Tierschutz, while TSchG and TSchV were absent
(#707). Every claim an agent drew from that hit would be anchored to a real, openable BV
section, and the answer would still be wrong, because the norm that actually governs was
missing and **nothing in the response could say so.**

That is ADR-0033's *"fluent citation of a provision that does not exist"* failure with one extra
step: the citations are all real. Only the conclusion is fabricated.

*(The corpus has since changed — #707/PR #721 landed and `q=Hund` now returns the
Tierschutzverordnung. The specific numbers above are historical. The structural gap is not:
nothing in the contract can state coverage, whatever the corpus happens to contain.)*

### Why the existing `coverage` block does not close it

`/v1/norm-hierarchy/{jurisdiction_id}` already returns a `coverage` object with
`covered_levels` / `missing_levels`, and it was built for exactly this purpose. It is real
coverage and it stays. But it cannot carry the load, for four reasons:

1. **It is level-granular, and the miss is instrument-granular.** In the failure above, the
   federal level was *covered* — the BV is federal. `missing_levels` was therefore correct and
   silent about the only thing that mattered: that the two federal acts governing the question
   were absent. Coverage that reports a level as held while the governing instrument inside it
   is missing does not prevent the fabrication it exists to prevent.
2. **It says nothing about freshness or provenance.** A corpus acquired yesterday and one
   acquired eighteen months ago are indistinguishable in its response. #709 asks for "as of
   when, from which source version"; the hierarchy walk answers neither.
3. **It is not enumerable.** The caller must already hold a `jur_*` id. There is no way to ask
   *"what do you hold at all?"*, so coverage cannot be surveyed, only spot-checked.
4. **It is a different question.** It is a traversal — *what governs this place* — and
   overloading it with corpus inventory would make one endpoint answer two questions whose
   correct behaviour under absence differs.

## Decision

### 1. Coverage is a first-class, queryable read model: `GET /v1/coverage`

A new path on `legal-search`, alongside `/v1/citations/stats` (which is the same idea applied to
the citation graph, and the precedent this follows). It reports, for a scope the caller names —
jurisdiction, authority, document type, norm level, optionally as-of a date — how many documents
the corpus holds, when the newest of them entered it, and which source versions produced them.

### 2. The load-bearing rule: coverage is a claim about the corpus, never about the law

This is the entire risk of the feature. A coverage endpoint that a caller can misread as
*"no such law exists"* is worse than no coverage endpoint, because it converts a cautious
agent into a confident one.

So the contract is built so that the misreading is not available:

- The holding enum is exactly `held | not_held`. **There is no value meaning "does not exist",
  "no such law", or "confirmed absent", and none will be added.** If a future requirement seems
  to need one, that is a requirement to revisit this ADR, not to extend the enum.
- `not_held` is specified as *"the search index contains no document matching this scope"* —
  a statement about our holdings, in the first person, with no projection onto the world.
- Every response carries `basis: "index"`, so a caller can see the answer's evidentiary base
  without reading prose.
- A jurisdiction id the platform does not recognize is returned in `unrecognized_jurisdiction_ids`
  and produces **no group at all**. A typo must never come back as `not_held` — "we hold nothing
  for `jur_ch_zurich`" reads as a coverage fact when the truth is that the caller misspelled
  `jur_ch_zh`.

**The corpus is a subset of the law by construction, and no endpoint over it can ever be
evidence of what the law does not contain.** The most this API can honestly support is a
refusal: *"I do not hold the governing norm for this question, so I will not answer it."*
That is the answer ADR-0033 §2 asked for, and it is sufficient.

### 3. Freshness is reported as what it is, and not as currency

`last_processed_at` is `max(processed_at)` over the group — the moment the newest document in
that scope entered the corpus. It is **not** evidence that the source was re-checked at that
time, and therefore not evidence that the corpus is current. A jurisdiction whose law changed
last week and whose last acquisition ran a year ago reports a year-old timestamp and *no*
indication that anything is stale, because the index does not know.

Naming it `last_processed_at` rather than `last_updated_at` or `freshness` is deliberate: the
field is exactly as strong as its name.

Answering *"when did we last check?"* requires run history, which lives in platform-control.
See §5.

### 4. Coverage lives in legal-search, and the acquisition half does not

Two different questions are both called "coverage", and conflating them is the second way this
feature could lie:

| Question | Fact type | Owner |
|---|---|---|
| *What does the corpus hold?* | index state, changes on every projection | **legal-search** |
| *What were we asked to acquire, and did it succeed?* | source/blueprint/run lifecycle | **platform-control** |

`legal-search` owns the first because it *is* the index — every field in the response is derived
from data it already holds, in one aggregation, with no external call.

It must **not** answer the second. It has two ways to try and both are worse than not trying:

- **Call platform-control at request time.** This introduces a runtime dependency on the read
  path, against the precedent already set in `core/norm-hierarchy`: the jurisdiction tree is
  consumed as a build-time export (`contracts/vocabularies/jurisdiction-hierarchy.json`,
  ADR-0004) explicitly *"rather than calling it at request time"*. Coverage would also make
  legal-search's availability depend on platform-control's.
- **Bake a snapshot at build time.** The vocabulary precedent works because the jurisdiction
  tree cannot change between deploys. Run history changes constantly. A baked snapshot would
  make the endpoint state a freshness claim that is itself stale — an endpoint that lies, which
  is the outcome this ADR exists to avoid.

So the split is not a scoping convenience. It is the honest boundary.

### 5. What is deliberately deferred

Named here so they are visible as gaps rather than discovered as surprises:

- **Acquisition-scope coverage on platform-control** — *"is any source even configured for this
  jurisdiction, is it enabled, when did it last succeed?"* This is the strictly stronger
  refusal: *"we have never attempted to acquire this"* is a much better thing to tell an agent
  than *"we hold nothing."* It is a separate PR on a separate service. #693's blueprint
  inventory — merged as of 2026-07-19 — is the natural place to hang it: it already
  surfaces per-template lock state (`enabled` / `live_ready` / `launchable`), which is
  exactly the "were we even asked to acquire this?" half that legal-search cannot see.
- **Coverage annotation on search responses.** The `q=Tierschutz` failure happened on
  `/v1/search`, and a caller that only searches never sees `/v1/coverage`. Attaching a coverage
  block to `SearchResponse` is the fix that most directly addresses the measured incident. It is
  held back only because #701 is mid-flight on the same paths and the same contract file.
- **Instrument-level coverage** — *"do you hold SR 455?"* `/v1/citations/resolve` already
  answers this deterministically (`resolved: false` for a norm we do not hold, never a
  similarity guess), but it is framed as citation resolution and conflates *"we do not hold it"*
  with *"we cannot parse your string"* under `unresolved_reason`. Separating those is the
  cheapest remaining coverage win.
- **Completeness-within-a-scope.** We cannot say *"we hold all federal animal-protection law."*
  Nothing in the platform knows the denominator. Any future attempt at this must state the
  denominator's source, or it is fabrication with a percentage attached.

### 6. A broken coverage endpoint must fail loudly, never quietly

Coverage has a uniquely bad failure mode. When search breaks it returns no results and
someone notices. When *coverage* breaks it reports **"we hold nothing"** — and an agent
faithfully relays that as a refusal. A false refusal is a lie the caller cannot detect.

So when the index cannot support the aggregation, the endpoint answers **503 with the
cause named**, rather than degrading to empty buckets. This is not a rough edge; it is the
decision. Softening the query until a drifted index accepts it is the wrong fix #675 first
shipped, and AGENTS.md already forbids it: fix the index, never the query.

This was verified live, not theorized. Against the local stack on 2026-07-19,
`documents-read` is entirely dynamically mapped — `authority_ids` and `in_force_until` do
not exist and `source_version_id` is `text` — and the endpoint correctly refused to
answer. Reindexed into a canonically-mapped copy of the same 77 documents, it answered.

## Consequences

- ADR-0033 §2's refusal capability becomes reachable, and `check_in_force` / `norm_hierarchy`
  (§3) gain the coverage precondition they were specified against. This lands **before** step 6
  (MCP), per ADR-0033 §4's build order — the tool layer gets a coverage tool to wrap instead of
  needing one invented inside it.
- `legal-search` gains a sixth module (`coverage`) following the established
  controller/service/repository-interface/adapter shape (ADR-0008).
- The contract grows a non-locked path. `/v1/coverage` is deliberately left out of
  `locked_paths` in `contracts/manifest.yaml` while its shape is validated against real agent
  use; it should be locked once an MCP tool depends on it.
- We accept that coverage remains **level- and scope-granular**, not instrument-granular, and
  that the specific `q=Tierschutz` incident is therefore mitigated rather than closed by this
  ADR alone. The deferred items in §5 are what close it.
- The cost of getting this wrong is asymmetric and is worth restating: an over-cautious coverage
  API produces refusals a human can override. An over-confident one produces legal advice with
  no law behind it.

## Alternatives considered

**Extend `/v1/norm-hierarchy`'s `coverage` block instead of adding a path.** Rejected for the
four reasons in Context. Chiefly: it requires a jurisdiction id the caller must already have, so
coverage could never be surveyed, and its correct behaviour under absence (report a missing
*level*) is not the behaviour coverage needs (report a zero *count* for a named scope).

**Put coverage on platform-control, which knows more.** Rejected as the primary surface.
platform-control knows about sources, blueprints and runs — but not about what actually reached
the index, which is the fact an agent needs before answering. It is also not the surface an agent
calls; ADR-0033 §3 builds the tool layer over legal-search. The right outcome is both, split as
in §4, and legal-search is the half that unblocks the acceptance test.

**Report a coverage percentage or a completeness score.** Rejected outright. Every such number
needs a denominator — how much law *exists* for this scope — and the platform does not have one
and cannot get one. A completeness score would be the single most dangerous field we could ship
here: it would look like the answer to "is this corpus good enough?", and it would be invented.

**Do nothing; let callers infer coverage from empty results.** Rejected — this is the status quo
that #709 filed, and the measured `q=Tierschutz` result is the evidence it does not work. It
also makes every retrieval bug indistinguishable from genuine absence, which means the platform
cannot even tell *itself* when it is broken.
