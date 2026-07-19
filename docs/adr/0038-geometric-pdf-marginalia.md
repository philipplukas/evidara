# ADR-0038: Separate the Randtitel band geometrically, and do not adopt Docling for PDFs

Status: Proposed
Date: 2026-07-19
Deciders: Document-intelligence / Platform
Amends: [ADR-0037](0037-binary-artifacts-and-layout-aware-pdf.md) §3 (the column-detection
signal) and §4 (the quality gate). ADR-0037 §1 (binary `ProviderResource`), §2 (PDF as a
pipeline modality) and its choice of **pdfplumber as the library** all stand.
Related: ADR-0033 (agentic legal reasoning — the corpus must be trustworthy), ADR-0010,
ADR-0014. Refs #650, #590, #584.

## Context

ADR-0037 chose `pdfplumber` and separated the marginal-heading band ("Randtitel") from the
body column by projecting word bounding boxes onto the x-axis and splitting on whitespace
gutters. It shipped green, on a **synthetic** reportlab fixture, because the real Zurich
ordinance could not be fetched in that sandbox (ADR-0037 §4 says so explicitly).

The real PDF is now available (AS 554.510, „Vollzugsvorschriften zum Hundegesetz").
Measured against it, ADR-0037's normaliser corrupts the document it was written for.

### The x-projection signal does not exist in this document

| Measurement (AS 554.510, page 1) | Value |
|---|---|
| Body column right edge (max x1) | **492.6** |
| Randtitel band left edge (min x0) | **498.2** |
| ⇒ actual gutter | **5.6pt** |
| Intra-sentence word gap, p50 | 3.9pt |
| Intra-sentence word gap, **p90** | **6.5pt** |
| `_detect_columns` join tolerance (as shipped) | 23.8pt |

The gutter separating a marginal heading from the body is **narrower than ordinary word
spacing inside a body sentence**. At p90 the gap the algorithm must *not* join is smaller
than the gaps it *must* join. No join tolerance separates them, so the page collapses to a
single column (verified: 1 column, x0=102.8 → x1=571.8) and the Randtitel splices into the
sentence:

> „die Führung des **Organisation** Hundeverzeichnisses"

This is **not a tuning problem.** X-projection is the wrong signal for this document class.

A second, independent defect: `_blocks_for_page` only treated columns entirely *left* of the
body as marginal. The ordinance is set as a booklet — recto pages carry the Randtitel on
the **right** (x 498.2–571.8), verso pages on the **left** (x 17.7–94.7). Half the marginal
headings were unreachable by construction.

The synthetic fixture hid both defects: it placed the Randtitel in the **left** margin with
a generous gutter. That is the specific reason this bug shipped green, and it is why the
regression fixture is now the real PDF.

### The first attempt — routing PDFs through docling — was tried and rejected

#650 proposed docling, and a first implementation of this ADR did exactly that: docling
extracted the text, and a post-pass string-matched each geometrically-detected Randtitel out
of the paragraph docling had merged it into.

**It passed locally and failed in CI, on the same PDF and the same commit.** Locally docling
produced the clean sentence and the post-pass lifted 8 of 8 labels. In CI, docling produced
a flat text dump with the splice intact, `Hun- deverordnung` unhealed, and the running
header spliced into the body:

> „…die Führung des **Organisation** Hundeverzeichnisses…"
> „…haben je Kalender- **Abgabe an die Gemeinde und** jahr Folgendes zu leisten…"

The relevant property here is not that docling scored worse. It is that **docling's output
for the property we depend on is environment-dependent** — it varies with model
availability, the `opencv` build, and whether a Hugging Face download succeeded. Its failure
mode is a silent degradation to top-to-bottom reading order, and the metadata still said
`pdf_extractor: docling`. For a legal corpus, an extractor that silently swaps correct text
for corrupted text depending on the machine is a worse defect than the one being fixed — it
is precisely the class of silent corruption ADR-0033 exists to prevent.

That attempt also required making docling a core dependency with a baked model set,
taking the runtime image from **843 MB to 4.08 GB** and PDF normalisation from 0.07s to
~11.7s cold. ADR-0037 §3's footprint and reproducibility objections to docling were
correct, and the bake-off did not refute them.

### What the failed attempt proved, and kept

The one part that worked in **both** environments was the geometry: a pdfplumber pass that
identifies which words are marginal. It found 8 of 8 Randtitel, on both band sides,
deterministically, offline, in ~0.1s. That component is the actual fix, and docling was
never load-bearing for it.

The signal is **line-start clustering**, not x-projection. Body text is set flush to one
left margin, so line-start x-positions cluster hard at the body edge (34 of 50 lines on
page 1 start at x = 103). A marginal band is a second, much smaller cluster far from that
edge (5 lines at x = 498). Justified body text scatters its *word* x0 values — which is why
x-projection fails — but never its *line-start* values.

## Decision

### 1. Keep pdfplumber. Replace the signal, not the library

`normalize/marginalia.py` detects the marginal band by line-start clustering, on either
side of the body, and returns a `PageSplit` partitioning the page's words into body and
band. `normalize/pdf.py` **subtracts** the band's words from the word stream and lays out
what remains.

This is set subtraction, not string matching. Once the band's words are gone from the
stream, no downstream pass can put them back inside a sentence — the splice is impossible
by construction rather than repaired after the fact. Subtracting the band also leaves an
ordinary single column behind, so reading order becomes trivial.

Guards keep a genuine two-column body from being shredded into "headings": a candidate band
must be narrow (≤ 35% of page width) and text-poor (≤ 25% of the page's characters).

### 2. Do not adopt docling for PDFs

`application/pdf` does not route through `ingest/docling_adapter.py`. Docling stays an
**optional extra** (`.[docling]`) for the *text* modalities it was already wired for
(HTML/XML/plain, `DI_PARSER_BACKEND=docling`), where its output is not load-bearing for
sentence integrity.

Consequently the runtime image stays at 843 MB, there is no Torch stack, no model bake, no
`HF_HUB_OFFLINE` sealing, and no network dependency at parse time.

### 3. Layout is recovered from type geometry

Everything docling was wanted for is available from pdfplumber's own font metadata:

- **Headings** — bold face at or above the modal body size. Size above modal ⇒ level 1
  (the title), at modal ⇒ level 2 (`A. Allgemeine Bestimmung`). A heading that wraps
  across two lines is emitted as one block.
- **List items** — Swiss literas (`a. `, `b. `, `c. `), with wrapped continuation lines
  kept inside the item they continue.
- **Paragraphs** — split on baseline steps exceeding 1.4× the page's own modal line pitch
  (measured: pitch 14.0pt, within-paragraph steps 14.0–14.7, between-paragraph 20.7–25.6).
- **Running headers and folios** — dropped from the flow when they sit wholly in the outer
  8% of the page. Left in, they splice the document's own title into a provision.
- **Footnotes** — the trailing run of sub-body-size type; kept as their own blocks, never
  merged into a body paragraph.

### 4. De-hyphenation is explicit

Wrapped words are rejoined (`Hundehaltungsvoraus-` / `setzungen` ⇒
`Hundehaltungsvoraussetzungen`), including when the hyphen is extracted as a detached
token (`ob -` / `liegt`). Without this a query for the compound cannot match the document
at all — the same class of silent corruption as #643.

An elided compound is **not** healed: `Halter-` / `und Hundedaten` keeps its hyphen,
because healing it would fabricate the word `Halterund`. The following conjunction is the
signal that distinguishes a wrap from an elision.

### 5. Randtitel are emitted as headings preceding their provision

Each detected label becomes its own heading block (`level: 3`, `attrs.marginal: true`,
with a slug anchor) positioned before the first section its vertical span reaches. A label
is a *heading of* the provision, not a fragment inside it.

## Consequences

### Result on the real ordinance

| | ADR-0037 (x-projection) | Docling attempt | **This ADR** |
|---|---|---|---|
| „Führung des **Organisation** Hundeverzeichnisses" (spliced) | yes | env-dependent | **no** |
| „Führung des Hundeverzeichnisses" (contiguous) | no | env-dependent | **yes** |
| De-hyphenation | `Hundehaltungsvoraus- setzungen` | env-dependent | **healed** |
| Randtitel recovered as headings | 0 of 8 | 8 of 8 local, 0 of 8 in CI | **8 of 8** |
| Title / section headings / list items | none | yes | **yes** |
| Runtime image | 843 MB | 4.08 GB | **843 MB** |
| Normalisation time | 0.07s | ~11.7s cold | **0.11s** |
| Deterministic across environments | yes | **no** | **yes** |
| Network/models at parse time | none | HF models | **none** |

### The quality gate that replaces ADR-0037 §4

The regression fixture is the **real PDF**, committed at
`document-intelligence/tests/fixtures/zh_as_554_510.pdf` (Swiss official texts carry no
copyright, Art. 5 URG). The synthetic reportlab fixture is retained but demoted: it is
skipped when the `test` extra is absent, and the real-PDF tests are **not** — a suite that
silently skips the load-bearing tests is exactly how the splice shipped green in the first
place.

### Scope and honest limits

- **This is one document class.** The line-start signal is validated on AS 554.510 and on
  synthetic single- and two-column fixtures. Other cantons' typesetting is unproven; each
  new source needs its real PDF added to the fixtures before `live_ready` flips.
- **No OCR.** An image-only PDF still yields an empty IR flagged `pdf_no_text_layer`,
  never fabricated body text. Unchanged from ADR-0037.
- **Footnote markers stay inline** as bare digits (`…vom 14. April 2008 1 und…`). They are
  not spliced *text*, but they are not marked up either.
- **`live_ready` for `gemeinde_http`** is unblocked by this change (#650 blocked it), which
  in turn unblocks the #628/M13 dog question.

## Deferred / follow-ups

- Structured footnote markers (link the inline digit to its footnote block).
- Article-level block nesting (`Art. 1` as a parent of its Absätze) — today the IR is flat.
- OCR for image-only PDFs.
- Re-evaluate docling for PDFs only if it ships a pinned, offline-by-default model set
  whose output is byte-stable across environments. Determinism, not accuracy, is the bar
  it failed.
