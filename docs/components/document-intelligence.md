# Document Intelligence

## Purpose

Turn immutable artifact bundles into canonical structured document intelligence. Document-intelligence transforms heterogeneous upstream content into stable `Document` and `Section` outputs, processing manifests, and published downstream surfaces.

It also owns non-canonical enrichment surfaces that are derived from published documents but are not canonical legal truth. The first such enrichment is extractive commentary insights: source-backed commentary anchors with evidence refs, confidence, review state, and deterministic validation scores.

## Current state

Initial implementation scaffolding now exists under `document-intelligence/`. The component now has a Python package skeleton, tolerant inbound event parsing, bundle-manifest and artifact loading for local files and `gs://`, minimal HTML and XML normalization with shared-IR section extraction, explicit published-surface definitions, an in-memory sink plus a Delta-backed sink, offline JSON Schema validation helpers, SQL renderers for published-surface registration under `src/document_intelligence/bootstrap/`, and bundle/adapter/CLI tests for the first processing path.

For the current M4 slice, freeze the primary happy path on Firecrawl-acquired HTML bundles with one primary document artifact. The existing RIS-style XML path remains useful regression coverage, but it is not the required deployment path for the first end-to-end searchable slice.

The production processing pipelines are still not fully implemented. Spark-native runtime wiring, CI/CD deployment integration for Terraform + Bundles, richer XML source-family coverage, citation extraction, jurisdiction resolution, and stricter final contract hardening are still pending.

See [Document Intelligence Implementation Plan](document-intelligence-implementation-plan.md) for the planned architecture and phased delivery approach.

## Source of truth

- Delta tables for canonical documents, sections, and processing manifests
- Delta tables for non-canonical enrichment surfaces, starting with `published_commentary_insights`
- Published DI surfaces for downstream consumers
- Unity Catalog lineage for DI-internal job, table, and published-surface lineage
- Processing logic in Databricks workflows
- `contracts/schemas/document.schema.json`, `contracts/schemas/section.schema.json`, and `contracts/schemas/processing-manifest.schema.json`
- `contracts/schemas/commentary-insight.schema.json` for extractive commentary insight records

## Responsibilities

### Minimal v1

- Read immutable artifact bundle manifests and artifacts
- Normalize and parse raw content
- Produce canonical `Document` and `Section` entities
- Assign `document_revision`
- Publish exact immutable downstream refs

Document-intelligence should lean on Databricks-native lineage for internal traceability, while still emitting Evidara contracts for any lineage or lifecycle state that must cross into other components.

### Boundary

- **Does own:** normalization, parsing, profile selection, canonical entities, document revisions, published surfaces, Databricks pipelines
- **Also owns:** non-canonical extractive enrichment generation and scoring, including commentary insight surfaces
- **Does NOT own:** source lifecycle, approvals, acquisition checkpoints, search projection logic

### HTML normalization (v1)

The built-in HTML normalizer uses `html.parser` for common block tags (`p`, headings, list items, table cells, etc.). When no blocks are extracted (for example, prose only inside `<div>`), it falls back to tag-stripping with whitespace normalization. Normalized IR metadata includes `html_parse_used_fallback` when that fallback runs. Embedded chrome (`iframe`, `form`, `object`, `embed`, `picture`, `video`, `audio`, `track`, `map`, plus script/style/`header`/nav/footer/aside) is skipped to stabilize body text. If `feed()` raises on malformed markup, recovery uses the same strip path and sets `html_parse_recovery` to `exception`.

### Quarantine — the text-level law assertion (ADR-0047)

A manifestation whose **extracted text** cannot support the claim that it is law does not
become a canonical document. It is *quarantined*: nothing is written to
`published_documents` / `published_sections`, no `document.processed` event is emitted (so
nothing reaches legal-search), and a `processing_manifests` row is written with
`status: quarantined` and a `quarantine` block carrying the reason and the measurements.

This is the gap the two acquisition gates leave. `acquisition_core.artifact_guard` judges
the bytes as received; `acquisition_core.content_gate` counts legal-text markers but
abstains on `application/pdf`. A structurally valid PDF whose text is a cover sheet, a
consent interstitial or nothing at all therefore passes acquisition end to end, and
judging it needs extraction — which lives here.

The judgment is `normalize/quarantine.py`. Four checks, in order (the first that fires
names the reason, so the recorded slug is the actual defect and not a downstream symptom):

| Check | Reason slug | Applies to | Exit |
|---|---|---|---|
| `pdf_no_text_layer` set by the PDF normaliser | `no_text_layer` | all | implement (OCR) |
| Normalisation produced no blocks / no text | `no_sections_extracted` | all | fix |
| Extracted characters below the floor | `below_content_floor` | modalities `content_gate` abstains on | fix or implement |
| Legal-text markers below the floor | `below_content_floor` | modalities `content_gate` abstains on | fix or implement |

The reason vocabulary is closed (ADR-0047 §3) and mirrored in
`contracts/schemas/processing-manifest.schema.json`.

**Configuration.** Both floors default on — `DI_QUARANTINE_MIN_EXTRACTED_CHARS` (200) and
`DI_QUARANTINE_MIN_LEGAL_MARKERS` (1). The marker floor deliberately differs from
`content_gate`'s 3, on measured evidence: the shortest real law this repo holds (the BS
municipal dog-tax decisions, `tests/fixtures/bs_municipal_hundesteuer.json`) carries **two**
genuine markers, and scored three only because of `Artikel` inside LexFind's change-table
boilerplate. A floor of 3 had zero headroom against real municipal law. The relation that
is enforced is that DI is never *stricter* than acquisition.

DI also reads per-source floors from `di_overrides.quarantine_min_extracted_chars` /
`di_overrides.quarantine_min_legal_markers`, but **no producer emits them** —
`di_overrides` is set nowhere in `platform-control/src`. Until one exists, the only live
control is the environment variable, which moves the floor for every source at once. A
malformed override leaves the configured floor in place; an explicit `0` disables that
floor, which is a supported escape hatch, not a bug.

**Scope, stated plainly: the text-level invariant now holds for PDF and for most HTML.**
The legal-text floors skip HTML/XML on the theory that `content_gate` judged them at
capture. That theory used to cover three of thirteen providers — only the ones inheriting
`PortalHttpProviderBase` (Canton/Bundesland/Regione). It now covers **eight**: those three,
plus `lexfind_api` (whose call is the deliberate `application/pdf` abstention),
`gemeinde_http`, `fedlex_sparql`, `ch_court_decisions` and `deterministic_http`.

Five remain outside it, and four of those are decisions rather than omissions:

- `ris_ogd` — the marker floor assumes one document is one **act**. RIS publishes one
  document per §/Artikel/Anlage, and BGBl. III Kundmachungen are prose. Measured
  2026-09-03, a floor of 3 refused 15 of 40 genuine documents (38% of
  `ris_ogd_bundesrecht`'s yield), including a 0-marker CMR Kundmachung and a `BrKons`
  norm carrying exactly 2. **RIS HTML/XML therefore reaches DI marker-checked by
  neither gate** — the largest remaining case for the HTML exemption below.

- `eur_lex_sparql` — `_preferred_languages` defaults to `["en"]`, and `content_gate`'s
  marker vocabulary is DE/IT. EU English writes "Article 5", which carries no `art.`,
  `§` or `Abs.`, so the gate would refuse honest captures. Closing it needs an EN/FR
  vocabulary, which `tests/test_quarantine.py` pins across both components.
- `legifrance` — same vocabulary problem in French, and `readiness=SCAFFOLD`.
- `cassette` — offline replay of already-captured bytes.
- `firecrawl` — the real remaining hole. Its pages arrive at
  `firecrawl_webhook_service.py`, a capture path outside the provider modules that calls
  neither gate and guesses the content type.

The matrix is asserted, not described:
`platform-control/tests/unit/test_capture_guard_coverage.py` fails when a registered
provider's capture path stops matching its recorded decision, and when a provider is
registered with no decision at all.

**Visibility.** `di_quarantined_documents_total{reason}` (Prometheus, on the consumers'
existing `/metrics`), a `document_quarantined` structured log line, the consumer outcome
label `quarantined` in `di_messages_total`, and the `processing_manifests` row itself.

**Not a failure, not a DLQ item.** Processing completed; the output is what we should not
trust. The message is acked, not naked — replay changes nothing until the missing class is
implemented. Do not route quarantine through the DLQ (`docs/runbooks/dlq-triage-and-replay.md`),
whose remedy is replay.

## Minimal next tasks

- [x] Define canonical `Document` schema
- [x] Define canonical `Section` schema
- [x] Define `ProcessingManifest` schema
- [x] Land initial local Python scaffold under `document-intelligence/`
- [x] Adapt the scaffold from the earlier single-artifact intake to `artifact_bundle.available` plus immutable bundle manifests
- [x] Implement GCS-native bundle-manifest and artifact reads
- [x] Implement Delta-backed canonical persistence and published-surface writes
- [x] Implement `document.processing_status.updated` and `document.processed` emission against the settled contracts
- [x] Add schema validation, golden bundles, and adapter/CLI tests
- [x] Define initial published surface schemas explicitly
- [x] Add SQL/bootstrap scaffolding for published-surface registration
- [x] Add an XML-first second source family with RIS-style fixture coverage
- [x] Add always-on runtime wiring for `artifact_bundle.available` consumption
- [x] Define source/jurisdiction profile registry
- [x] Harden HTML parsing and broaden source-family support deliberately

## Minimal v1 Outcome

One bundle can be transformed into:

1. One or more canonical document revisions
2. Canonical sections from day one
3. Processing manifests with exact published refs
4. `document.processed` events emitted per document revision

When `DI_ENABLE_COMMENTARY_INSIGHTS=true`, commentary documents can also produce non-canonical `published_commentary_insights` rows. These rows are extractive only and must carry evidence refs; they are not embedded into canonical `Document` truth.

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Jurisdiction and authority resolution |
| Next | Citation extraction |
| Later | Optional OpenLineage export if cross-platform lineage becomes necessary |
| Later | Document relationships |
| Later | Quality scoring |
| Later | Richer profile registries and resolution audits |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Databricks | Processing runtime and orchestration |
| Delta tables | Canonical and manifest storage |
| Unity Catalog lineage | DI-internal lineage and governance |
| GCS | Read raw artifacts and bundle manifests |
| Pub/Sub | Consume acquisition events, emit status and publication events |

## Document Service (read boundary)

Downstream **document detail** in the request path must not read Delta ad hoc. The **Document Service** is the DI-owned HTTPS read API for published document bodies (Docling JSON), as specified in:

- `contracts/api/document-intelligence.openapi.yaml`
- [ADR-0010: Document Content Format](../adr/0010-document-content-format.md)

Endpoints (contract):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/documents/{document_id}` | Full Docling JSON |
| `GET` | `/v1/documents/{document_id}/lean` | Lean JSON for BFF → frontend |
| `GET` | `/v1/documents/{document_id}/text` | Plain-text fallback |

Phase 1 may implement this as a Databricks SQL REST gateway or a thin FastAPI service; the **OpenAPI spec is the contract** either way. The **legal-search BFF** is the primary caller.

### Durable canonical persistence on the self-hosted stack

`build_processing_pipeline` selects the sink from the canonical surface URIs
(`DI_PUBLISHED_DOCUMENTS_URI` / `DI_PUBLISHED_SECTIONS_URI` / `DI_PROCESSING_MANIFESTS_URI`,
or `DI_SURFACES_ROOT_URI`):

- **Set** → `DeltaCanonicalSink` writes `published_documents` / `published_sections` /
  `processing_manifests`, and `store_from_env()` returns a `DeltaPublishedDocumentStore` that
  reads the same surfaces. On the Hetzner stack these point at Delta tables on MinIO
  (`s3://evidara-lakehouse/canonical/...`); credentials/endpoint come from `DI_S3_*` and are
  translated to `deltalake` `storage_options` (`AWS_ENDPOINT_URL`, `AWS_ALLOW_HTTP`,
  `AWS_S3_ALLOW_UNSAFE_RENAME` for the single-writer consumer). A native `IcebergCanonicalSink`
  on MinIO remains the longer-term follow-up; Delta-on-S3 is the production-safe interim.
- **Unset** → `InMemoryCanonicalSink` and an `EmptyPublishedDocumentStore`.

**Failure mode:** if the surface URIs are unset (or misconfigured) on `di-consumer`/`document-service`,
processed documents are never durably stored, `GET /v1/documents/{id}/lean` misses, and
legal-search projections fall back to thin metadata (title `Document {id}`, no sections/citations).
Recovery is to set the surface URIs in the `evidara-config` ConfigMap and reprocess.

### HTML sectioning

Sections are the retrieval unit: a lawyer searches for a *provision*, not a statute. The HTML
normalizer (`normalize/html.py`) therefore distinguishes two kinds of tags:

- **Leaf text tags** (`p`, `li`, `td`, `th`, `blockquote`, `pre`) and headings (`h1`–`h6`) each
  become exactly one `Block`.
- **Structural containers** (`article`, `section`, `main` — plus `div`, which is transparent) are
  recursed into. They never become blocks themselves, so a `<h6>` nested inside
  `<article id="art_36">` stays a heading. Loose text sitting directly inside a container with no
  leaf tag around it is still captured, and flushed as a paragraph block.

`sectionize/html.py` then splits on heading blocks. Each section carries:

- `metadata.anchor` — the nearest enclosing element id (e.g. `art_36` for a Fedlex provision). This
  is the stable, citable address of the provision.
- `metadata.ancestor_titles` / `parent_title` / `parent_anchor` — the enclosing heading chain, so an
  article knows its chapter (`Art. 36` → `2. Titel: Grundrechte` → `1. Kapitel: Grundrechte`).
- `depth` — derived from the heading level.

**Failure mode:** if a container is treated as a leaf text tag, it buffers every nested heading and
paragraph into a single block, all headings disappear, and the whole statute collapses into one
section (issue #573: the Bundesverfassung produced 2 sections, one of them 197 KB). The
`ch_fedlex_bv_html` golden fixture — the real, full Bundesverfassung — guards this with a minimum
section count and a maximum per-section length.

## Key Contracts

- **Consumes:** `artifact_bundle.available`
- **Consumes:** reference snapshot sets published by platform-control
- **Produces:** `document.processing_status.updated`
- **Produces:** `document.processed`
- **Planned next:** `document.withdrawn`
- **Exposes (sync):** Document Service OpenAPI for published document bodies
- **Schemas:** `Document`, `Section`, `ProcessingManifest`
- **Enrichment schema:** `CommentaryInsight`

## Testing

See [Document Intelligence Testing](testing/document-intelligence-testing.md) for the full testing strategy.

Key tests:

- Unit tests for parsing helpers and section construction
- Offline JSON Schema validation for `Document`, `Section`, `ProcessingManifest`, and current event contracts
- Offline JSON Schema validation for `CommentaryInsight`
- Golden document tests with representative bundles
- GCS loader tests with stubbed storage client behavior
- Delta sink tests with real local Delta tables
- Durable lean round-trip test: golden fixture → `DeltaCanonicalSink` → `GET /lean` serves real title/sections/citations (`tests/test_lean_durable_roundtrip.py`)
- CLI smoke test for bundle processing
- Invariant checks on provenance, revisions, and section ordering
- One minimal end-to-end processing path

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes break parsing | Golden bundle tests detect regressions |
| Section structure changes unexpectedly | Invariant checks and section-count drift checks |
| Reference snapshot changes alter outputs unexpectedly | Record snapshot set refs in `ProcessingManifest` |
| Pipeline runs but publishes stale or partial data | Emit `document.processed` only after canonical-ready manifest state |
| A document is admitted with no legal text in it (empty IR, scan, cover page) | Quarantine gate on extracted text (ADR-0047); `tests/test_quarantine.py` pins both directions — the image-only PDF is withheld, the real ZH ordinance is not |
| The two legal-text gates drift into different opinions about what law looks like | `tests/test_quarantine.py::MarkerVocabularyDriftTests` reads `acquisition_core/content_gate.py` and fails when the marker vocabulary, threshold or assessable content types diverge |
