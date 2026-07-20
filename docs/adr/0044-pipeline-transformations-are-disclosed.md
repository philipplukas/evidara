# ADR-0044: A Pipeline Transformation Is Disclosed Where the Text Is Read

## Status

Proposed

## Date

2026-07-20

## Context

The document pipeline makes editorial decisions about legal text and records
none of them. Measured on the corpus as it stands on 2026-07-20, after the CH
Gemeinde Zürich acceptance run (#735):

| Decision the pipeline makes | Where it is visible |
|---|---|
| Footnote apparatus excluded from `body_text` (#754) | nowhere |
| Randtitel lifted from the body and reattached as a section heading (#650, ADR-0041) | nowhere |
| Running headers and folios stripped as page furniture | nowhere |
| The ordinance's own citation `554.510` dropped entirely (#755) | nowhere |
| Extractor profile, compliance policy, gates applied | nowhere |
| Which acceptance gates *did not run* (`skipped_gates`, #744) | a markdown file in a scratchpad |

Each decision is individually defensible. #754's exclusion is correct: footnote
markers survive as bare digits, so `"§ 20 Hundeverordnung 4"` is shaped exactly
like `"§ 20 Abs. 4"`, and an agentic layer reading apparatus as operative text
cites a provision that does not exist. Stripping page furniture is correct.
Separating the Randtitel is correct — leaving it inline produced
`"die Führung des *Organisation* Hundeverzeichnisses"`.

The problem is not the decisions. It is that **a lawyer reading the document
cannot tell any of them were made.** They see continuous prose and have no way
to know that four statutory cross-references were removed from it, or that the
text they are citing has been reflowed from a two-band page layout.

This is the same defect the repo has now paid for three times in a different
guise. #744 established that *a gate that did not run must not be reported as one
that passed*, because a check returning green without executing is worse than no
check. #605, #675 and #713 are the same shape in the index-mapping layer. The
guardrail was applied to verification and never to transformation, even though
the failure mode is identical: **a surface that looks complete while something
was silently removed.**

ADR-0033 names the failure this enables — a system that demos convincingly and
misleads. A document whose apparatus has been stripped without disclosure looks
*more* trustworthy than one that shows its workings, which is precisely backwards.

An independent audit of the running product on 2026-07-20 found the consequence
already present: provenance is entirely absent from the document detail page. No
source URL, no fetch time, no revision, no run id. `source_version_id`, `run_id`,
`processing_manifest_id` and `document_revision` all exist in the index mapping
and none reach the API entity. A user cannot answer "where did this text come
from and is it current" at all.

## Decision

**Every transformation that removes, moves or rewrites content is recorded at
the moment it is made, and disclosed on the surface where the resulting text is
read.**

Three parts, in dependency order.

### 1. The IR carries a transformation record

`NormalizedDocumentIR` gains a structured record of what the normaliser did —
what was removed, what was reclassified, and by which rule. The information
already exists at the moment of the decision; today it is discarded. `pdf.py`
knows it lifted four footnote lines and nine Randtitel; nothing downstream can
ask.

This is a contract change and the reason this is an ADR rather than a ticket.

The record is **descriptive, not diagnostic**: it states what happened to the
document, not how the code reached that conclusion. Log lines remain the place
for the latter.

### 2. The document surface discloses it

The legal-search document detail states, in the reader's terms:

- where the text came from (source URL, fetched at, run, revision)
- what was removed from the body and remains available (footnote apparatus,
  with the citations retrievable rather than merely absent)
- what was restructured (marginal headings separated into section headings)
- whether the document is currently in force, or that this is unknown

"Unknown" is a first-class answer. ADR-0033 already requires the four-valued
in-force model to be able to say it, and `pipeline._resolve_in_force_window`
already refuses to guess — *"a wrong date is worse than a missing one"*. The
display must preserve that rather than rendering absence as silence.

### 3. The operator surface discloses the rules that ran

The run detail in platform-control shows which extractor profile and compliance
policy applied, which gates ran, and — load-bearing — **which gates did not**.
`skipped_gates` is computed today by the acceptance harness and dies in a file
under `/tmp`. The operator deciding whether to flip a template's config key
should see it in the panel where they flip it, not in a markdown bundle they
have to be told about.

## Consequences

**Positive:**

- A cited passage can be traced to its source and its transformations. That is
  the minimum bar for a legal-research product, and the corpus cannot be
  audited without it.
- The apparatus excluded by #754 stops being invisible. Those citations are
  legally meaningful; "removed from body text" and "not present in the document"
  become distinguishable.
- The agentic layer ADR-0033 anticipates can consume the transformation record
  and know what it is *not* seeing — which is the difference between an answer
  and a confident guess.
- `skipped_gates` reaches the person whose decision it exists to inform.

**Negative:**

- A contract change to the IR, with a migration cost for every normaliser
  (`pdf`, `html`, `xml`) and every consumer.
- Disclosure surfaces are product work, not just plumbing: a footnote panel that
  nobody reads is not obviously better than the status quo, and getting it wrong
  adds clutter to a document view that is already dense.
- There is a real risk of over-disclosure. A reader does not need to know that
  seven blank lines were collapsed. The record must cover **content-affecting**
  decisions and stop there, or it becomes noise that trains people to ignore it —
  which would be worse than the current silence.

## Alternatives considered

### A. Log it and move on

Emit the decisions as structured log events; leave the surfaces alone. Rejected:
logs answer an engineer's question during an incident, not a lawyer's question
while reading. The audience that needs this is the one that will never see a log,
and the failure mode — citing text whose apparatus was silently removed — happens
in the reading, not in the pipeline.

### B. Keep everything in `body_text` and disclose nothing

Reverse #754 so nothing is removed. Rejected: it reinstates the defect —
`"§ 20 Hundeverordnung 4"` reading as `§ 20 Abs. 4`. Inclusion without
distinction is not disclosure, it is a different corruption.

### C. Provenance only, no transformation record

Ship the source URL and fetch time; skip what the normaliser did. Rejected as
insufficient rather than wrong: knowing where a document came from does not tell
a reader that four cross-references are missing from the passage they are about
to cite. It is, however, the correct *first* increment — see the sequencing note
below.

### D. Do it per-normaliser, ad hoc

Let each normaliser surface what it likes. Rejected: the pdf normaliser would
disclose marginalia and the html one would not, so absence of disclosure would
carry no information. A guarantee is only useful if it is uniform.

## Sequencing

Deliberately staged, because part 1 is a contract change and parts 2–3 are not:

1. **Provenance on the document surface** (alternative C) — uses fields that
   already exist in the index and merely fail to reach `DocumentEntity`. No
   contract change; closes the audit's most-cited gap.
2. **`skipped_gates` on the run detail** — the data exists; it needs a home in
   the panel.
3. **The IR transformation record** — the contract change, once 1 and 2 have
   shown what the surfaces actually need.

Doing 3 first would be designing a contract against imagined requirements.

## Related

- ADR-0033 — agentic legal reasoning; the demo-that-lies-convincingly guardrail
  and the four-valued in-force model
- ADR-0041 — geometric PDF marginalia; the transformation that has the largest
  effect on the text today
- #744 — a gate that did not run must not be reported as one that passed; this
  ADR is the same rule applied to transformation rather than verification
- #754 — footnote apparatus excluded from `body_text`
- #755 — the ordinance's own citation is not indexed
- #760 — `regeste` populated on every document, rendered nowhere
- #628 — the coverage loop; an operator cannot accept a corpus they cannot audit
