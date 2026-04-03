# ADR-0010: Document Content Format — DoclingDocument

## Status

Proposed

## Date

2026-03-29

## Context

The frontend currently renders legal document content as raw HTML strings via `dangerouslySetInnerHTML`. This approach has several problems:

- **Security** — XSS risk; requires sanitization with DOMPurify.
- **No structure** — paragraphs, marginals, and cross-references are opaque text.
- **No search highlights** — OpenSearch returns highlight fragments, but merging them into an HTML blob is fragile.
- **No annotations** — cannot attach annotations to specific paragraphs.
- **Tight coupling** — the API embeds CSS classes in responses.

We need a structured document format that:

1. Is produced by the ingestion pipeline (Databricks/Docling).
2. Can be indexed in OpenSearch for full-text and vector search.
3. Can be rendered in the frontend as React components.
4. Supports legal-specific semantics (marginals, cross-references, Regeste, Erwägungen).
5. Does NOT require inventing a custom schema from scratch.

Separately, multiple services need to access the canonical document store (Delta Lake):

- **document-intelligence** (Databricks) writes DoclingDocuments.
- **legal-search BFF** (NestJS) reads full documents for the detail view.
- **OpenSearch indexing** reads documents for chunking and embedding.

Per ADR-0003, *"No component reads another component's storage directly"* and *"Data flows between storage layers through contracts (events and APIs)."* We need a clean access pattern for Delta Lake.

## Decision

### 1. DoclingDocument as the canonical format

Use IBM [Docling](https://github.com/docling-project/docling)'s `DoclingDocument` as the document content representation across the entire stack:

| Layer | Format | Notes |
|-------|--------|-------|
| Ingestion (Databricks) | `DoclingDocument` (Python, Pydantic) | Produced by `DocumentConverter` + custom backends for Fedlex/RIS |
| Canonical store (Delta Lake) | `DoclingDocument` JSON | Full lossless representation including bounding boxes, confidence |
| Search index (OpenSearch) | Flattened text + structured metadata | Produced by `HybridChunker`; no bounding boxes |
| API response (BFF → Frontend) | Lean `DoclingDocument` JSON | Stripped of layout metadata (bounding boxes, confidence scores) |
| Frontend rendering | `@docling/docling-core` TypeScript types | Custom React renderer maps labels to design-system components |

### 2. Docling extension points for legal domain

Use Docling's built-in extension mechanisms, not a custom format:

- **Custom Backend** (`DeclarativeDocumentBackend`): For Fedlex AKN XML and RIS XML sources. Maps legal structures (articles, paragraphs, Regeste) directly into DoclingDocument nodes with domain labels.
- **Enrichment Pipeline**: Post-conversion step that annotates nodes with legal NER, cross-references, and marginal numbers. Stored in `item.metadata`.
- **`HybridChunker`**: Structure-aware chunking for OpenSearch indexing. Handles text flattening, token-aware splitting, and metadata enrichment. No custom code needed.

### 3. Delta Lake access via Document Service

To respect ADR-0003's constraint that components don't read each other's storage directly, introduce a thin **Document Service** as the API boundary for Delta Lake access.

**Phase 1 (now):** A simple read API exposed by document-intelligence:

```
GET /documents/{id}          → Full DoclingDocument JSON
GET /documents/{id}/lean     → Without bounding boxes / confidence
GET /documents/{id}/text     → Plain text (for debugging / fallback)
```

Normative HTTP contract (paths, ids, response media types): [`contracts/api/document-intelligence.openapi.yaml`](../../contracts/api/document-intelligence.openapi.yaml) (`/v1/documents/...`).

This can be implemented as:

| Option | Implementation | When to use |
|--------|---------------|-------------|
| **Databricks SQL REST API** | Query Delta table via Databricks SQL endpoint | Simplest; works today; pay per query |
| **Delta Sharing** | Open protocol; NestJS reads via delta-sharing connector | Multi-consumer; governed access; no Databricks compute |
| **Thin Python service** | FastAPI wrapper reading Delta via `delta-rs` | Full control; deploy on Cloud Run |

**Recommendation for Phase 1:** Use the **Databricks SQL REST API** — zero new infrastructure, the BFF calls Databricks SQL on demand, Delta table is already there.

**Phase 2 (scale):** If query volume grows or latency requirements tighten:

- **Delta Sharing** for governed multi-consumer access without Databricks compute costs.
- **Redis/Memcached cache** in front of the document API for hot documents.
- **S3/GCS materialization** of lean DoclingDocument JSON at ingestion time, so the BFF reads pre-computed files instead of querying Delta.

**Phase 3 (mature):** If multiple teams or external partners need access:

- Full Delta Sharing server with per-consumer credentials and audit logging.
- CDC (Change Data Capture) from Delta → event stream for real-time downstream updates.

### 4. Frontend rendering

The frontend uses `@docling/docling-core` for TypeScript types and a custom React renderer:

```tsx
function DoclingRenderer({ doc }: { doc: DoclingDocument }) {
  return (
    <>
      {iterateDocumentItems(doc).map(({ item, level }) => {
        switch (item.label) {
          case "section_header":
            return <SectionHeading key={item.self_ref} level={level} text={item.text} />;
          case "paragraph":
            return (
              <Paragraph
                key={item.self_ref}
                text={item.text}
                marginal={item.metadata?.marginal}
                highlights={item.metadata?.highlights}
                legalRefs={item.metadata?.legal_refs}
              />
            );
          case "table":
            return <LegalTable key={item.self_ref} table={item} />;
          default:
            return <p key={item.self_ref}>{item.text}</p>;
        }
      })}
    </>
  );
}
```

Search highlights from OpenSearch are merged into `item.metadata.highlights` by the BFF before returning the response.

## Rationale

- **DoclingDocument is already an established standard** — Pydantic-based, JSON-serializable, with TypeScript types (`@docling/docling-core`) and frontend components (`@docling/docling-components`).
- **Docling handles the hard parts** — PDF extraction, layout detection, table reconstruction, reading order. We don't reinvent this.
- **The extension model covers legal semantics** — custom backends, enrichment pipeline, and metadata are designed extension points, not workarounds.
- **HybridChunker → OpenSearch is a solved problem** — Docling + OpenSearch integration is documented and battle-tested.
- **One format end-to-end** reduces the number of transformations and eliminates "impedance mismatch" bugs between layers.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Raw HTML (current) | XSS risk, no structure, no highlights, no annotations |
| Custom `ContentBlock[]` JSON | Requires inventing and maintaining a custom schema; duplicates work Docling already does |
| Akoma Ntoso (AKN) XML | XML parsing complexity in frontend; great as input format but not as wire format |
| Portable Text (Sanity) | No legal semantics; designed for CMS, not document intelligence |

## Consequences

- All document content flows as DoclingDocument JSON — no more `contentHtml: string`.
- The frontend renderer must handle Docling's label vocabulary (extensible via the enrichment pipeline).
- Delta Lake access is mediated through an API boundary, not direct reads.
- The team must understand Docling's extension model (custom backends, enrichments, chunking).
- Search highlights and cross-references are injected at the BFF layer into the DoclingDocument metadata.
