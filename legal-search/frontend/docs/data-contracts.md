# Data Contracts

> BFF view model types, domain model mapping, and API integration points.

---

## Frontend View Models

The frontend renders **view models** — opaque data shaped by the BFF. The UI never reasons about domain entities directly.

> Source: [`types.ts`](../src/lib/types.ts)

### Search Result

```typescript
interface SearchResultViewModel {
  id: string;
  type: string;                    // "law" | "court_decision" | "rechtssatz" | "commentary"
  title: string;
  subtitle: string;
  snippet: string;                 // Serif-rendered content excerpt
  structuralContext?: string;      // e.g. "Part 2 > Chapter 3 > § 754"
  badges: BadgeViewModel[];
  metadataRows: MetadataRow[];     // Label-value pairs (jurisdiction, date, court)
  relatedCounts: RelatedCount[];   // Pivot links: "12 Entscheide", "3 Kommentare"
  actions: ActionViewModel[];      // Context actions (open source, cite)
  contentLanguage?: ContentLanguage;
}
```

### Detail

```typescript
interface DetailViewModel {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  breadcrumbs: string[];           // Jurisdiction > Law > Chapter path
  metadata: MetadataRow[];
  contentText?: string;            // Document body, plain text; blank lines separate paragraphs
  contentLanguage?: ContentLanguage;
  tabs: TabViewModel[];            // Available detail tabs
  relatedGroups: RelatedGroup[];   // Grouped related items
  references: ReferenceGroup[];    // Incoming/outgoing citation references
  annotations: AnnotationViewModel[];
  localStructure?: { items: LocalStructureItem[] };  // Document TOC
}
```

### Supporting Types

| Type | Fields | Purpose |
|------|--------|---------|
| `BadgeViewModel` | `label`, `colorKey`, `iconKey?` | Type badges (law, decision, etc.) |
| `MetadataRow` | `label`, `value`, `iconKey?` | Key-value metadata display |
| `RelatedCount` | `label`, `count`, `href?` | Pivot link with count |
| `ActionViewModel` | `label`, `icon`, `href?` | Context action button |
| `ContentLanguage` | `display`, `original`, `isTranslation`, `label?` | Translation indicator |
| `TabViewModel` | `key`, `label`, `count?` | Detail panel tab |
| `RelatedGroup` | `groupLabel`, `items: RelatedItem[]` | Grouped related materials |
| `ReferenceGroup` | `direction`, `items: ReferenceItem[]` | Cites / cited-by groups |
| `AnnotationViewModel` | `title`, `content`, `provenance?`, `sourceCount?`, `confidence?` | AI/editorial annotation |
| `LocalStructureItem` | `id`, `label`, `active` | Document TOC entry |
| `FilterViewModel` | `key`, `label`, `type`, `options`, `selected` | Filter facet (checkbox/chip/dropdown/toggle) |
| `ContextChip` | `key`, `label`, `active`, `iconKey?` | Jurisdiction/language chip |
| `SearchContextViewModel` | `jurisdictions`, `languages`, `sourceTypes`, `exactMatches?` | Context bar state |

### Workspace Types

| Type | Fields | Purpose |
|------|--------|---------|
| `ResultSet` | `source`, `items`, `scopeLabel` | Current result set with provenance |
| `ResultSetSource` | `{ type: "search", query }` or `{ type: "pivot", label, parentSource }` | Where results came from |
| `TrailEntry` | `id`, `title`, `type`, `timestamp` | Focus history entry |
| `PinnedItem` | `id`, `title`, `type` | Pinned item reference |

---

## Domain Model → View Model Mapping

> Source: [Domain Model](../../.gemini/antigravity/brain/76bdaed8-db34-4dba-9eaf-4d9b1f082d2e/domain_model.md)

The BFF transforms backend domain entities into frontend view models:

```
Domain (Postgres)              BFF Transform              View Model (React)
─────────────────              ─────────────              ──────────────────
Document (polymorphic)    ──►  select type-specific   ──► SearchResultViewModel
  + attributes                 fields, compute badges,    + BadgeViewModel[]
  + jurisdiction_code          format metadata rows       + MetadataRow[]
  + Section[]                                             + structuralContext

Document + Article        ──►  join articles,          ──► DetailViewModel
  + Chunk (hidden)             render contentText,        + contentText
  + Citation[]                 group references,          + ReferenceGroup[]
  + Commentary[]               attach annotations         + AnnotationViewModel[]

Citation (edges)          ──►  resolve to documents,   ──► ReferenceGroup
  + semantic_type              group by direction         "Cites" / "Cited by"
  + source/target              label by semantic type

int_document_relations    ──►  group by relation type  ──► RelatedGroup[]
  (materialized view)          compute counts              + RelatedCount[]

dim_sections              ──►  build breadcrumbs +     ──► breadcrumbs[]
  + chapter_path               local TOC                  + LocalStructureItem[]

fct_article_annotations   ──►  attach to article      ──► AnnotationViewModel
  + annotation_type            detail view                + provenance
  + confidence                                            + confidence
```

### Key Design Decisions

1. **Chunks are hidden** — search returns snippets mapped to articles/documents, never raw chunks
2. **Polymorphic documents** — `type` field drives badge colors, available metadata fields, and tab configuration
3. **Article is the UI pivot** — BFF endpoint `GET /bff/articles/:id` assembles text + annotations + decisions + citations in one call
4. **Related counts are computed** — `RelatedCount[]` computed at query time from citation/relation joins, not stored
5. **Jurisdiction hierarchy** — `jurisdiction_code` is a leaf FK into the jurisdictions seed table, BFF resolves display labels and breadcrumbs

---

## API Endpoints

### BFF (Frontend-facing)

| Endpoint | Returns | Drives |
|----------|---------|--------|
| `GET /v1/search` | `SearchResponseView` (`results`, `facets`, `totalResults`) | Center panel result list + filter facets |
| `GET /v1/search/context` | `SearchContextView` | Context bar chips/tabs |
| `GET /v1/documents/{document_id}` | `DetailView` | Right panel detail view |
| `GET /v1/documents/{document_id}/sections` | `SectionSummary[]` | Local structure navigation |

### REST (Data layer)

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/documents` | List/filter documents |
| `GET /v1/documents/{id}` | Single document |
| `GET /v1/documents/{id}/articles` | Articles within a law |
| `GET /v1/documents/{id}/chunks` | Document chunks |
| `GET /v1/citations` | Citation graph edges |
| `GET /v1/statistics/*` | Dashboard KPIs (coverage, courts, laws, citations, pipeline) |

### Pagination

All list endpoints use **cursor-based** pagination (`meta.next_cursor`). UI should implement infinite scroll or "load more", not numbered pages.

---

## Runtime Data Sources

Frontend runtime now uses the generated API client against live BFF endpoints.
`mock-data.ts` remains test fixture material, not the runtime source of truth.
