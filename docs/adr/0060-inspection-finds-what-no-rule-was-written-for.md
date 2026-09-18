# ADR-0060: Inspection finds what no rule was written for

## Status

Proposed

## Date

2026-09-18

## Context

The pipeline already refuses a great deal, and refuses it well. Three layers of
deterministic checking are in place and each one is load-bearing:

| Layer | What it asserts |
|---|---|
| `acquisition_core.content_gate` | legal-marker density on the captured bytes — at least 3 markers, so a navigation shell is not mistaken for law (#631) |
| `normalize.quarantine` | a closed taxonomy of five refusal reasons; ADR-0047 is explicit that over-quarantine is itself a failure |
| `quality.invariants` | structural invariants — a document has a title, sections belong to their parent, ordinals ascend |
| the acceptance harness | per-corpus gates: expected content type, URL pattern, title regex, indexed language, in-force window |

Every one of these is a **rule written against a failure somebody had already
seen.** That is their strength and it is exactly their limit.

### What one week measured

On 2026-09-17/18, five of those gates failed against corpora that were entirely
correct, and each failure was a shape nobody had named yet:

| Gate | The corpus it was wrong about |
|---|---|
| content gates read the raw artifact | a PDF corpus, where the raw body is empty and the text exists only after extraction (#1015) |
| a 10 KB content floor | Stadt Zürich's Hundevorschriften — 3,080 characters, and a genuine municipal ordinance (#1016) |
| legal-marker density counted only `Art.` | Basel-Stadt, which drafts in `§` — 126 markers read as none (#1017) |
| the first-article gate knew only `Art. 1` | an 1874 treaty numbered `Art. I` to `Art. VI` (#1019) |
| the read-back gate had no self-hosted auth | every self-hosted run, reported NOT EVALUATED (#1015) |

Four of the five were marker- or threshold-shaped: the rule encoded one drafting
tradition and met another. French `Article premier` and Italian `Art. 1-bis` are
already queued to do it a sixth and seventh time.

### And what the rules did not catch at all

In the same week, 30 documents reached the index carrying a title fabricated from
their own id, empty `jurisdiction_ids` and no language. Every deterministic gate
passed them. They were found because one acceptance run happened to assert an
expected title on a template that happened to declare one — and the template that
caught it was unrelated to the 30.

That is the shape of the problem. A rule catches the failure it was written for.
Nothing in the pipeline asks *"is this document unlike everything around it?"*

## Decision

**Add inspection alongside the rules: checks that can find a defect without
having been told what it looks like.** Three mechanisms, in increasing cost, and
the cheap one carries most of the weight.

### 1. Distributional outliers — the corpus is its own control

Within one source version, compute the spread of a handful of measures already
produced by the pipeline: body length, legal-marker count, section count,
citation count, title length, language.

Flag a document that is an extreme outlier **against its own peers**. No
threshold is chosen in advance and no drafting tradition is assumed: a corpus
that numbers in `§` establishes its own marker distribution, and a municipal
ordinance corpus establishes its own length.

This would have caught the 30 immediately — 30 documents with an empty
`jurisdiction_ids` in a corpus where every peer has one is not a subtle signal.
It would not have needed to know what a placeholder title is.

**This is not a score.** ADR-0042 refuses completeness percentages because a
number needs a denominator, and the same objection applies to "quality: 0.87".
The output is a **finding**: *this document is unlike its peers in this
respect*. A finding names a document and a measure. It never ranks a corpus.

### 2. Cross-source corroboration — already built, one provider deep

`lexfind_api` re-fetches a sample of captured documents from the **canton's own
host** and compares md5. That catches "the mirror served something else" without
knowing how it differed, because it uses an independent source of truth. It is
the strongest signal available anywhere in the pipeline.

It is currently one provider's feature. It should be a capability any provider
with a second reachable source can declare.

Note what it already gets right and must keep: an unreachable authority is
recorded and warned about, and does **not** fail the run — the mirror exists
precisely to survive that. A corroboration check that cannot run reports that it
could not run.

### 3. LLM inspection — on the flagged set, and a random sample

For documents flagged by (1), failing (2), or **drawn at random**: ask whether
the title matches the content, whether the text is a complete legal instrument or
a fragment, whether it is a website's navigation chrome.

That is semantic judgement, which no rule expresses. It would have caught
`Consolidation: 0.142.115.141 - 1875-01-29` sitting where
`Niederlassungsvertrag mit dem Fürstentum Liechtenstein` belonged.

**The random sample is the half that matters.** Inspecting only flagged documents
finds only what the flagger already knows how to flag — the same closed loop the
deterministic rules are already in. A small random draw is the only mechanism
here that can discover a shape nobody has named. It is the direct answer to the
week described above.

Cost is bounded by construction: flagged documents plus a fixed small sample per
run, never the corpus.

## Constraints this must hold

Three, each of which the repo has already paid to learn.

- **A finding, never a score.** See ADR-0042. The moment this emits a number
  between 0 and 1, somebody will average it.
- **`not_inspected` is not `passed`.** If the model is unreachable or the corpus
  too small for a distribution, that is reported as a gate that could not run —
  the `excluded` / `not_evaluated` distinction #744 already drew, and the exact
  defect fixed in #1030 where an unavailable enrichment was papered over with a
  fabricated value.
- **It ships with a document it is known to reject.** A gate that cannot go red
  is decoration, and this repo has shipped several. The 30 placeholder-titled
  records and the 1875 treaty are both available as fixtures.

## What is out of scope

- **This is not ADR-0033 §4's reasoning MCP server**, and must not become it.
  It inspects ingest quality. It answers nothing about law.
- **It does not gate publication** in its first form. It produces findings an
  operator reviews. Turning a finding into a refusal is a second decision, taken
  once the false-positive rate is measured rather than assumed — the alternative
  is a new way to withhold real law, which is what #1016 and #1017 each did.
- **It does not replace the deterministic gates.** They are cheap, exact, and
  catch the known shapes on every document rather than a sample. Inspection is
  what stands behind them.

## Consequences

### The corpus becomes the control, so small corpora are honest about it

Outlier detection needs peers. A source version with three documents has no
distribution, and the check must say so rather than flag all three or none. This
is a real limit: today's most valuable corpora — a single municipal ordinance, a
two-document Tierschutz template — are exactly the ones it cannot serve. It
earns its keep as the corpus grows, which is also when manual review stops
scaling.

### An LLM in the ingest path, for the first time

`llm_extraction` already exists in the pipeline and is opt-in with a confidence
threshold. This is a second, narrower use: inspection rather than extraction, on
a sample rather than every document, and its output is a finding rather than a
field written to canonical. The distinction should stay visible in the code, or
the two will be conflated and the inspection results will end up in `metadata`.

### Findings need somewhere to live

A finding that nobody reads is the DLQ problem again (ADR-0058): this week
proved that an unread signal and an absent one are the same thing. The refusal
ledger #911 already proposes the surface — *what we will not claim, and why* —
and inspection findings belong there rather than in a new place.

### The honest expected value

This will not catch everything, and its first version will mostly re-find things
the rules already catch. The case for it is narrower than "quality": it is the
only mechanism proposed here that can surface a failure mode **before** someone
names it, and the week this ADR documents cost four wrong diagnoses and five
gate fixes to name five of them.
