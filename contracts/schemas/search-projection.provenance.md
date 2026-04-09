# Search Projection — Field Provenance

Companion to `search-projection.schema.json`. Documents ownership, source, and failure behavior for every field in the OpenSearch projection.

## Canonical Fields (copied from document-intelligence output)

| Field | Owner | Source | Required? | Failure if missing |
|---|---|---|---|---|
| `document_id` | document-intelligence | canonical output | **yes** | Projection rejected |
| `title` | document-intelligence | canonical output | **yes** | Projection rejected |
| `jurisdiction` | document-intelligence | canonical output (enum) | no | Facets and badges omit jurisdiction |
| `document_type` | document-intelligence | canonical output (enum) | no | Generic badge, generic actions |
| `authority_name` | platform-control → document-intelligence | `source_defaults.authority_name`, forwarded via `document.processed` | no | Subtitle omits court/authority label |
| `official_citation` | document-intelligence | canonical metadata `official_citation` | no | Citation trust row omitted |
| `original_language` | document-intelligence | canonical metadata `original_language` | no | Translation label loses explicit source-language state |
| `translation_status` | document-intelligence | canonical metadata `translation_status` | no | Content-language label falls back to implicit behavior |
| `is_official` | document-intelligence | derived from `source_origin_kind`, forwarded via `document.processed` | no | Official-source trust row omitted |
| `language` | document-intelligence | extraction result | no | Language facet/badge omitted |
| `structural_path` | document-intelligence | structural analysis | no | No breadcrumbs in detail view |
| `effective_date` | document-intelligence | metadata extraction | no | Date metadata row omitted |
| `lifecycle_status` | document-intelligence | `document.processed` event payload | no | Non-active documents lose explicit trust signal |
| `content` | document-intelligence | text extraction | no | No search snippets, no preview |
| `content_docling` | document-intelligence | docling pipeline (ADR-0010) | no | Detail view shows no structured content |
| `source_id` | document-intelligence | lineage (from platform-control) | no | Lineage broken |
| `processed_at` | document-intelligence | processing timestamp | no | — |

## Derived Fields (computed by projection builder)

| Field | Owner | Computation | Required? | Default | Failure if missing |
|---|---|---|---|---|---|
| `sections_count` | projection builder | `count(sections WHERE document_id = ?)` | **yes** | `0` | Tabs and related counts show 0 |
| `citations_count` | projection builder | `count(citations WHERE source_document_id = ?)` | **yes** | `0` | Citations tab shows 0 |
| `related_decisions_count` | projection builder | reverse citation join to `document_type = 'decision'` | no | `0` | Related counts omitted |
| `related_commentary_count` | projection builder | reverse citation join to `document_type = 'commentary'` | no | `0` | Related counts omitted |
| `content_preview` | projection builder | `truncate(content, 200)` | no | — | No preview available |

## Denormalized Fields (on citation projections)

These appear in citation-type OpenSearch documents, not in document projections.

| Field | Owner | Source | Required? | Failure if missing |
|---|---|---|---|---|
| `target_title` | projection builder | join on `target_document_id → document.title` | no | Citation shows raw reference only |
| `target_subtitle` | projection builder | join on `target_document_id → composed subtitle` | no | Citation subtitle omitted |
| `target_document_type` | projection builder | join on `target_document_id → document.document_type` | no | Citation not grouped by type |

## Runtime Fields (NOT stored — attached at query time)

| Field | Source | Notes |
|---|---|---|
| `snippet` | OpenSearch `highlight` API | Generated at query time from `content`. Not part of stored projection schema. |
| `relevance_score` | OpenSearch `_score` | Query-time relevance ranking. Not stored. |

## Nullability Policy

- **Required integer fields** (counts): always present, default `0`. Never omitted or `null`.
- **Optional string fields**: omitted when unavailable. Never `null`.
- **Optional object fields** (`content_docling`): omitted when unavailable.
- This aligns with ADR-0011 conventions for the BFF layer.
