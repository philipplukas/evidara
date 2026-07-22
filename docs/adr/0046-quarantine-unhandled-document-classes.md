# ADR-0046: Quarantine — the corpus holds only documents whose class we have implemented

Status: Proposed
Date: 2026-07-22
Deciders: Platform / Document intelligence
Related: ADR-0033 (agentic legal reasoning — the corpus must not fabricate), ADR-0030
(acquisition provider enablement — the two-key lock), ADR-0037 (binary manifestations),
ADR-0041 (layout-aware PDF normalisation), #631, #716, #731, #628

## Context

### The invariant we do not currently hold

A document reaches the canonical corpus today whether or not any code understood it.
Verified on `origin/main`:

- **An unreadable PDF becomes an empty document, not a failure.**
  `document-intelligence/src/document_intelligence/normalize/pdf.py:170` — when a PDF has
  no text layer, the normaliser emits an **empty IR** and continues, recording
  `pdf_no_text_layer: True`. The comment is honest about the intent: *"better than
  fabricating body text… flags the artifact as needing OCR downstream."* Nothing
  downstream acts on the flag.

- **The validator checks structure, not content.**
  `document-intelligence/src/document_intelligence/validate/validator.py` requires manifest
  fields to be present, refs to be well-formed, and — for `canonical_ready` — that the
  published refs **exist**. It never asks whether they point at anything.

- **The measurement already exists and is ignored.**
  `document-intelligence/src/document_intelligence/canonical/models.py:143-145` —
  `ProcessingManifest` carries `document_count`, `section_count`, `citation_count`. A stub
  yields `section_count: 0`. That number is computed, stored, and read by nothing.

- **HTML invents a handler rather than admitting it has none.**
  `document-intelligence/src/document_intelligence/normalize/html.py:239` — when the parser
  produces no blocks, it falls back to stripping tags and emitting the residue as a single
  paragraph. That is not "handling the class"; it is guaranteeing a non-empty output
  regardless of whether the input was understood.

Net effect: **the pipeline's default for "I do not understand this" is to emit a plausible
empty document and mark it ready.**

### Why this is a corpus-integrity decision, not a bug

ADR-0033 exists to prevent *"the confident fabrication the platform exists to prevent."*
Issue #628 named the recurring signature across this milestone: **the system substituted a
plausible value for "I don't know."** A truncated picker that looked complete. A hit count
that was really a page size. An absence claim derived from one section's sitemap.

An empty canonical document is the same defect at the corpus layer, and it is the most
damaging instance, because coverage is what the corpus is *for*. A document that is present
but empty reports coverage we do not have. For a human reader that is a confusing result;
for an agent answering ADR-0033's dog question it is a citation to nothing.

### Three failure classes, currently indistinguishable

1. **Not the format at all** — #716's 142-byte JavaScript redirect stub served where a PDF
   was expected; #631's SPA shell served as a statute. Detectable from the bytes.
2. **Valid PDF, no text layer** — a scanned ordinance **or** an image-only stub. These are
   *not distinguishable from each other*, which is why "empty ⇒ reject" is wrong: it would
   discard legitimate scanned communal law, precisely the corpus #584 targets.
3. **Valid document, text present, but not law** — a cover page, an error page, a
   consent interstitial. Requires extraction to detect.

Class 1 is a transport concern and is being handled at acquisition
(`acquisition_core/artifact_guard.py`). Classes 2 and 3 are semantic and belong here.

### Why the DLQ does not already solve this

A dead-letter queue holds work that **failed** — an exception, a retry budget exhausted
(`docs/runbooks/dlq-triage-and-replay.md`). Its remedy is *replay*: fix the transient
condition and the message succeeds.

A quarantined document did **not** fail. Processing completed and produced output we should
not trust. Replaying it changes nothing until someone implements the missing class. Same
queue shape, opposite remedy — conflating them would make the DLQ undrainable.

## Decision

### 1. The invariant

> **The canonical corpus contains only documents whose class has an implemented handler.**

Nothing reaches canonical by fallback, by default, or by producing an empty artifact that
satisfies a structural check.

### 2. Quarantine is an explicit terminal-for-now state with exactly two exits

A quarantined document is not an error and not a success. It is an **admission**, and it
resolves in one of two ways:

- **A failure in our logic** — the class *is* implemented and mishandled this instance.
  Remedy: fix, then re-process. This is a bug report with a reproducer attached.
- **A document class we have not implemented yet** — image-only PDFs needing OCR, a portal
  format we have never met, a manifestation type with no normaliser. Remedy: implement the
  class, then re-process the whole cohort.

Both are actionable and neither is silent. **That is the entire point:** the quarantine
queue is simultaneously the defect list and the product backlog for corpus coverage.

### 3. Quarantine carries a reason from a closed taxonomy

A free-text reason degrades into prose nobody groups by. Reasons are slugs, and the slug
determines which exit applies:

| Reason | Class | Exit |
|---|---|---|
| `no_text_layer` | 2 | implement (OCR) |
| `below_content_floor` | 2/3 | fix or implement |
| `no_sections_extracted` | 3 | fix |
| `unsupported_manifestation` | — | implement |
| `format_signature_mismatch` | 1 | fix (should not reach DI) |

New reasons require a taxonomy entry, so "miscellaneous" cannot become the largest bucket.

### 4. Fallbacks that invent a handler are removed, not kept as a safety net

`normalize/html.py:239`'s tag-stripping fallback is replaced by quarantine with
`no_sections_extracted`. A fallback that always produces output is indistinguishable, from
the outside, from a handler that works — which is exactly how this class of defect survives
review.

### 5. Quarantine rate is acceptance evidence

ADR-0030's two-key lock turns on operator-captured acceptance evidence. A source whose
acceptance run quarantines most of its documents has demonstrated that its class is *not*
handled, and **must not** earn `enabled: true`. The quarantine rate becomes a first-class
number in the acceptance record alongside captured/processed counts.

### 6. Quarantine must be visible or it is silent failure with extra steps

This is the failure mode this ADR is most likely to suffer. A queue nobody reads is worse
than no queue, because it *feels* like the problem is handled. Therefore:

- a count and per-reason breakdown exposed as a metric,
- an operator surface listing quarantined documents by reason and source,
- the number surfaced in the acceptance record (§5), where it is read by construction.

## Consequences

### Costs, stated plainly

- **Coverage will drop on paper, immediately.** Documents currently counted as corpus
  members will move to quarantine. This is the number becoming honest, not a regression —
  but it will look like one, and it must be communicated as such before it is measured.
- **Existing canonical documents were admitted under the old rule.** A backfill sweep is
  needed to find already-published empty documents. Until it runs, the invariant holds only
  for new work.
- **The queue needs draining capacity.** One operator. At municipal scale a 10% quarantine
  rate over thousands of documents is not triageable per-item — which is why the taxonomy
  (§3) matters: cohorts are resolved per *class*, not per document.
- **Over-quarantine blocks the corpus.** Floors that are too aggressive stall ingestion.
  Floors are therefore per-source config, not global constants: the honest minimum for a
  cantonal act is not the honest minimum for a one-article communal ordinance.

### What this buys

- "Documents in corpus" becomes a claim we can defend, which is the precondition for
  ADR-0033's acceptance test meaning anything.
- The unimplemented-class backlog stops being invisible. Today an image-only PDF produces a
  silent empty document; under this ADR it produces a queued, counted, named gap — and
  "we need OCR" becomes a measured requirement rather than an intuition.
- Refusal becomes correct behaviour. ADR-0033's acceptance test already admits a correct
  refusal as a pass. This extends the same standard from the answer to the corpus.

## Open questions

- **Does quarantine block a source version's promotion, or only flag it?** §5 says the rate
  is evidence; it does not yet say the threshold.
- **Is OCR in scope at all, or is `no_text_layer` a permanent decline?** This decides whether
  scanned communal law is reachable, and therefore part of #584's feasibility.
- **Where does the quarantine record live** — a DI-owned table, or a platform-control
  read model beside the existing lifecycle events? The operator surface argues for the
  latter; ownership of the judgment argues for the former.
