# ADR-0037: Binary artifacts end-to-end and a layout-aware PDF normaliser

> **Amended by [ADR-0041](0041-geometric-pdf-marginalia.md) (2026-07-19).**
> §1 (binary `ProviderResource`), §2 (PDF as a pipeline modality) and the choice of
> **pdfplumber** all stand.
> **The x-projection column detection in §3 is superseded**: measured on the real
> AS 554.510 PDF, the body/Randtitel gutter is 5.6pt against a p90 intra-sentence word gap
> of 6.5pt, so projecting words onto the x-axis cannot separate them and splices the
> marginal heading into the sentence. It also only looked *left* of the body, while the
> booklet layout puts recto Randtitel on the right. ADR-0041 replaces the signal with
> line-start clustering and subtracts the band from the word stream.
> **§4's synthetic fixture is the reason that defect shipped green** — the regression
> fixture is now the real PDF.

Status: Proposed (§3 signal and §4 gate superseded by ADR-0041)
Date: 2026-07-15
Deciders: Contracts / Platform / Document-intelligence
Related: ADR-0033 (agentic legal reasoning — the corpus must be trustworthy),
ADR-0010 (document content format), ADR-0014 (document-intelligence pipeline
integration), ADR-0030 (acquisition provider enablement lifecycle). Refs #590, #584, #589.

## Context

Swiss municipal law is largely **PDF-only**. The demo question ADR-0033 fixes —
"can the city ban a certain thing for dogs, year-round?" — is decided by a communal
ordinance (Zurich AS 554.510, „Vollzugsvorschriften zum Hundegesetz") whose URL is a
metadata landing page and whose operative text exists **only as a PDF**. There is no
HTML manifestation. This is not a Zurich quirk: it is the shape of the whole municipal
layer, ~2,000 communes behind it (#584).

Two structural blockers made that layer unacquirable — neither fixable inside a provider:

1. **The acquisition interface could not represent binary.** `ProviderResource.body`
   was typed `str` (`platform-control/src/acquisition_core/providers.py`). A PDF cannot
   be carried through acquisition at all — not badly, not at all. The `gemeinde_http`
   provider therefore *refused* PDF-only manifestations rather than emit a metadata stub.

2. **document-intelligence had no PDF path.** `document_intelligence/normalize/` shipped
   `html.py` and `xml.py` only; both the legacy and `docling` backends take
   `artifact_text: str`. An `application/pdf` artifact was read via `read_artifact_text`
   (a lossy text decode of raw bytes) and fell through to `normalize_plain_text_document`,
   which would normalise raw PDF binary.

### Naive PDF text extraction corrupts legal text

`pdftotext` (and `pdfplumber.extract_text` with default top-to-bottom flow) splice the
PDFs' marginal headings ("Randtitel") **mid-sentence**:

> „die Führung des **Organisation** Hundeverzeichnisses"

That is silently corrupted legal text: it indexes, it searches, it looks fine — and it is
wrong. This is exactly the "demo that reads as authoritative and isn't" failure ADR-0033
exists to prevent. A layout-aware extractor is **required**, not a text dump.

### What the wire contracts already supported

Importantly, the cross-service contracts already model binary content: the
artifact-bundle-manifest `storage_ref` (`contracts/common/storage-object-ref.schema.json`)
and the `raw-artifact-available` event both carry a free-form `content_type` and a
`byte_size`, and DI's primary-artifact selection already ranks `application/pdf`. The gap
was **not** the wire schema — it was the internal Python interface (`ProviderResource`)
and DI's text-only reading/normalisation assumption. This narrows the contract change to
an internal shared-shape widening plus a new pipeline modality; no `contracts/` schema
required a breaking change.

## Decision

### 1. Widen `ProviderResource` to carry bytes + a content type

`ProviderResource` now carries **exactly one** manifestation:

- `body: str | None` — text (HTML/XML/plain text), the existing path, unchanged for callers.
- `body_bytes: bytes | None` — binary (PDF), the new first-class alternative.

A `__post_init__` invariant enforces exactly-one-of. Two helpers give downstream code a
modality-agnostic view: `raw_bytes` (the payload used for checksums and durable storage —
UTF-8 of `body` for text, `body_bytes` verbatim for binary) and `is_binary`.

The raw-artifact pipeline (`acquisition_core/normalization.py`) hashes `raw_bytes`, so a
PDF and an HTML page are checksummed identically. The inline body is carried JSON-safely:
text verbatim under `inline_body`, binary base64-encoded under `inline_body_base64` with
an `inline_body_encoding` discriminator (a JSON payload cannot hold raw bytes).

Existing text callers are untouched — `body=` remains a keyword all providers already pass.

### 2. A layout-aware PDF normaliser producing the same IR

`document_intelligence/normalize/pdf.py` adds `normalize_pdf_document(pdf_bytes, artifact_id)`
producing the **same** `NormalizedDocumentIR` the HTML path produces, so sectioning,
citations and anchors work unchanged. The pipeline reads a PDF primary artifact as raw
bytes (`BundleLoader.read_artifact_bytes`, added alongside the existing
`read_artifact_text`) and routes it to the PDF normaliser before the parser-backend branch.

The normaliser is layout-aware: it uses word bounding boxes to detect vertical whitespace
gutters, separates the marginal-heading band from the body column by x-position, and only
then reconstructs reading order. A Randtitel is emitted as its own **heading block**
(carrying a slug anchor, exactly like a Fedlex `<article id=…>` heading) *before* the whole
body paragraph it labels — never spliced into the sentence. An image-only PDF with no text
layer yields an empty IR flagged `pdf_no_text_layer` (a candidate for OCR) rather than
fabricated body text.

### 3. Library choice: `pdfplumber`, not `docling`

We evaluated `docling` (referenced in the repo but never installed) against `pdfplumber`:

| | pdfplumber (**chosen**) | docling |
|---|---|---|
| Layout signal | word-level bounding boxes (x0/x1/top/bottom) — sufficient for margin/column separation | ML layout model |
| License | MIT | MIT, but pulls a large transitive stack |
| Footprint | pure-Python + pdfminer.six/pypdfium2 | multi-GB Torch stack |
| CI reproducibility | deterministic, no downloads | downloads models at runtime |
| Fit for this problem | coordinate-based margin/column separation is exactly what's needed | overkill |

`pdfplumber>=0.11,<0.12` is pinned as a **core** dependency (municipal PDF is a
first-class modality, not an opt-in extra). `PyMuPDF`/`fitz` was rejected on licensing
(AGPL). `docling` remains available behind its existing optional extra for future
ML-heavy needs but is not on the critical path.

### 4. Quality gate: an anti-splice regression test

`tests/test_normalize_pdf.py` pins the failure mode with the `Organisation` splice as the
fixture. It first asserts that a *naive* extraction really does splice (proving the fixture
is faithful), then asserts the layout-aware normaliser keeps the body sentence contiguous
and surfaces the Randtitel as a separate heading. The real Zurich PDF (AS 554.510) could
not be fetched in the sandbox, so the fixture is a **synthetic multi-column PDF** built with
reportlab that reproduces the marginal-splice mode deterministically.

## Consequences

- The municipal layer is now *representable and normalisable* end-to-end. Actually
  acquiring Zurich (flipping `gemeinde_http` to emit PDFs, wiring a municipal blueprint)
  is **#584** and deliberately out of scope here — #590 is the binary/PDF foundation only.
- No `contracts/` schema change was required; this ADR records that the widening was
  internal and documents why (the wire contracts already allowed `application/pdf`).
- New runtime dependency `pdfplumber` in document-intelligence.
- `read_artifact_bytes` is now part of the `BundleLoader` interface (local/GCS/S3/dispatch).

## Deferred / follow-ups

- Municipal acquisition slice (#584): provider emit + blueprint + Firecrawl disposition.
- OCR for image-only PDFs (flagged `pdf_no_text_layer`, not yet handled).
- Richer PDF heading-level inference (font-size/weight) and genuine multi-column bodies
  beyond the margin/body split; table extraction.
- Validating against the real AS 554.510 PDF once network acquisition lands.
