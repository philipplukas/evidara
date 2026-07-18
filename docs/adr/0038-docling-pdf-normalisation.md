# ADR-0038: Route PDF normalisation through Docling

Status: Proposed
Date: 2026-07-18
Deciders: Document-intelligence / Platform
Amends: [ADR-0037](0037-binary-artifacts-and-layout-aware-pdf.md) §3 (library choice) and §4
(quality gate). ADR-0037 §1 (binary `ProviderResource`) and §2 (PDF as a pipeline modality)
stand unchanged.
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

A second, independent defect: `_blocks_for_page` only treats columns entirely *left* of the
body as marginal. The ordinance is set as a booklet — recto pages carry the Randtitel on
the **right** (x 498.2–571.8), verso pages on the **left** (x 17.7–94.7). Half the marginal
headings were unreachable by construction.

The synthetic fixture hid both defects: it placed the Randtitel in the **left** margin with
a generous gutter. That is the specific reason this bug shipped green, and it is why the
regression fixture is now the real PDF.

### Bake-off on the real PDF

| | pdfplumber (ADR-0037) | docling |
|---|---|---|
| „Führung des **Organisation** Hundeverzeichnisses" (spliced) | **yes** | no |
| „Führung des Hundeverzeichnisses" (contiguous) | no | **yes** |
| De-hyphenation | `Hundehaltungsvoraus- setzungen` | `Hundehaltungsvoraussetzungen` |
| Structure | 6 flat blocks, no title | title, `A. Allgemeine Bestimmung` … `D.`, list items |
| Randtitel recovered as headings | 0 of 8 | 8 of 8 (after the post-pass below) |
| Time (in-image, warm) | 0.07s | 0.9s |

## Decision

### 1. `application/pdf` normalises through docling

`normalize_pdf_document` routes to a new byte-accepting entry point,
`normalize_pdf_with_docling(artifact_id=…, pdf_bytes=…)` in `ingest/docling_adapter.py`.

This also closes a structural incoherence: `normalize_with_docling` takes
`artifact_text: str`, so it could never accept a PDF, and `pipeline.py` routed PDFs before
the `parser_backend == "docling"` branch was ever reached. **`DI_PARSER_BACKEND=docling`
therefore still yielded pdfplumber output for every PDF.** PDFs now always use docling;
`parser_backend` selects between legacy and docling for *text* modalities only. That is
deliberate — no environment variable should be able to select silently-corrupted legal text.

While fixing this we found that the docling **text** path had never run either:
`doc.iterate_items()` yields `(item, tree_level)` pairs, and the adapter unpacked it as a
bare item, so `_item_text` returned `""` for every node, zero blocks were produced, and the
function silently fell back to the legacy normaliser on every call. Fixed here.

### 2. A geometry post-pass lifts the Randtitel (`normalize/marginalia.py`)

Docling preserves **sentence integrity** — it never interleaves the label mid-clause — but
it does not emit the Randtitel as its own block. It either appends it to the end of the
paragraph beside it ("…Sache des Sicherheitsdepartements. **Organisation**") or emits it as
a standalone text item at the wrong point in reading order (page 2's labels all land after
the final article). Both leave the label inside, or adjacent to, body text.

The post-pass is **geometric, not lexical** — no per-municipality string rules:

1. **Detect the band.** Body text is set flush to one left margin, so *line-start*
   x-positions cluster hard at the body edge (34 of 50 lines on page 1 start at x=103). A
   marginal band is a second, much smaller line-start cluster far from it (5 lines at
   x=498). Justified text scatters its *word* x0 values but never its *line-start* values —
   which is exactly why line starts separate the bands where x-projection cannot. Bands are
   accepted on either side of the body.
2. **Guard against real multi-column layouts.** A band must be narrow (<35% of page width)
   and text-poor (<25% of page text mass), or it is left alone.
3. **Heal wrapped labels.** A narrow band wraps aggressively ("Aufhebung bis-" /
   "herigen Rechts"), so hyphenated line breaks rejoin.
4. **Match by geometry, then lift.** A candidate block must be on the same page *and*
   vertically overlap the Randtitel. Exact match wins, then suffix, then containment. The
   label is removed from the body text and re-emitted as its own heading block (level 3,
   slug anchor, `attrs.marginal = True`) positioned before the provision it labels.
5. **Never invent.** A Randtitel matching nothing is left alone and counted in
   `metadata.pdf_marginalia.unmatched` rather than guessed at.

Result on AS 554.510: `{"detected": 8, "lifted": 8, "unmatched": []}`.

### 3. Docling is a core dependency, and its models are baked into the image

Moved from the optional `docling` extra (which nothing installed) into `[project]
dependencies`, alongside `pdfplumber`. The `docling` extra is removed.

**ADR-0037's CI-reproducibility objection is answered, not waived:**

- `DOCLING_ARTIFACTS_PATH=/opt/docling-models`, with layout + TableFormer weights
  downloaded **at build time**. OCR and the enrichment models are excluded.
- `HF_HUB_OFFLINE=1` is set *after* the bake, sealing the image.
- The build runs the real PDF through the real pipeline and **fails the build** unless the
  sentence is contiguous and all marginal headings are matched.
- Verified with `docker run --network none`: correct output, no network access.

Two build details worth keeping:

- **CPU-only torch**, installed from the PyTorch CPU index before docling resolves, so the
  multi-GB CUDA wheels never enter the image.
- **`opencv-python-headless`** replaces docling's `opencv-python`. The GUI build links
  against X11 libraries `python:3.12-slim` does not ship; without this, TableFormer fails to
  import at pipeline construction and *every PDF silently falls back to the splicing
  extractor*. The build gate caught this — it is precisely the failure mode this ADR exists
  to prevent, and it would have shipped green without an end-to-end build assertion.

### 4. The pdfplumber normaliser is retained as a flagged fallback

`normalize_pdf_document_pdfplumber` remains for when docling cannot run. Because it is
**known to corrupt this document class**, a fallback result is never presented as
equivalent: it sets `pdf_extractor="pdfplumber"` and `pdf_fallback_reason`, which downstream
can gate on.

## Consequences

### The cost: a much larger image

| | Before | After |
|---|---|---|
| `document-intelligence/Dockerfile` | **843MB** | **4.08GB** |

Roughly +3.2GB: torch (CPU) 750MB, docling models 506MB, opencv 153MB, transformers 109MB,
plus scipy/sympy and other transitive weight.

**ADR-0037's objections were real, and this ADR does not refute them.** Footprint, CI
reproducibility, and runtime model downloads were all genuine concerns, and the first is
simply *accepted* here — a 4.8x image is a real operational cost. What the bake-off refutes
is only ADR-0037's claim that *"coordinate-based margin/column separation is exactly what's
needed"*: on the real document that separation is not achievable from coordinates alone,
which is the one premise the whole choice rested on. Reproducibility and model downloads are
not accepted as costs — they are engineered away above.

We take the trade because silently corrupted legal text is not a cost we can pay. ADR-0033's
whole bet is a corpus that can be trusted; an ordinance that indexes cleanly and reads
authoritatively while saying something the law does not is the exact failure it exists to
prevent.

### Docling is better here, not perfect

Stated plainly so the next reader does not over-trust it:

- It does **not** emit the Randtitel as its own block — §2's post-pass exists for that.
- De-hyphenation is **partial**: `Hundehaltungsvoraussetzungen` heals, but `erho- ben` and
  `ob -liegt` survive in the output.
- It normalises en-dashes to hyphens (`Fr. 130.–` → `Fr. 130.-`).
- Footnote blocks are emitted inline at their page position, not collected.
- ~13x slower than pdfplumber per document (0.9s vs 0.07s, warm, in-image). Irrelevant at
  current volumes; revisit if bulk backfill becomes throughput-bound.

### Other consequences

- Docling being core means `Dockerfile.runtime-ingress` and `Dockerfile.document-service`
  also carry the torch stack. Only the first normalises PDFs; the document service does not
  and pays the weight for nothing. Slimming those is deferred, not solved.
- `tests/fixtures/zh_as_554_510.pdf` (217KB) is committed as the regression fixture. Swiss
  official texts carry no copyright (Art. 5 URG).
- OCR remains deferred (unchanged from ADR-0037). Image-only PDFs still yield an empty IR
  flagged `pdf_no_text_layer`. Enabling it later means: install `libgl1`/`libglib2.0-0`/
  `libxcb1`, add `with_rapidocr=True` to the bake, and flip `do_ocr`.

## Deferred / follow-ups

- Slim the non-normalising DI images so they do not carry torch.
- Complete de-hyphenation and en-dash preservation as a normalisation post-pass.
- Validate the marginalia detector against a second and third municipality's layout; the
  guards are principled but have been measured on exactly one document family.
- OCR for image-only PDFs.
