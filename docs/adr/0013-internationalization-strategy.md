# ADR-0013: Internationalization Strategy

## Status

Proposed

## Date

2026-04-01

## Context

Evidara serves legal professionals working with Swiss, Austrian, German, and Liechtenstein legal materials. Swiss federal law exists officially in three languages (German, French, Italian). The platform should support users who prefer different interface languages while preserving the integrity of legal content in its original language.

Currently:

- The frontend layout hardcodes `lang="de"`, but many BFF mapper labels are in English.
- Vocabulary files (`jurisdiction.json`, `document-type.json`) carry English-only labels.
- The BFF composes all display-ready strings (badges, facets, tabs, actions, metadata rows) and returns them as pre-composed labels. The frontend renders them as-is.
- No i18n infrastructure exists in any component.

## Decision

### Separate content language from UI locale

Two independent axes govern language in Evidara:

| Axis | What it is | Examples | Owner |
|------|-----------|----------|-------|
| **Content language** | The language a document was written in | A BGE decision in German, a federal law in French | document-intelligence (detected/assigned) |
| **UI locale** | The language the user sees the interface in | "Filter" → "Filtre", "Pin" → "Épingler" | Frontend (user preference) |

These axes are independent. A French-speaking user can read a German court decision — the document content stays German, but all UI chrome appears in French.

**The i18n system only translates UI chrome.** Document content is never translated by the UI layer.

### Domain vocabulary labels live in contracts

Locale-keyed labels are added to the vocabulary files in `contracts/vocabularies/`:

```json
"CH": {
  "label": "Switzerland",
  "labels": { "de": "Schweiz", "fr": "Suisse", "it": "Svizzera" },
  "iconKey": "ch"
}
```

This preserves vocabulary files as the single source of truth for domain terminology. The BFF resolves `labels[locale]`, with fallback to `label`, then fallback to the raw code.

**Principle: Domain vocabulary lives in contracts; UI composition lives in the BFF.**

### The BFF must be locale-aware

The BFF already composes and returns display-ready strings for:

- Badge labels
- Facet group labels
- Tab labels
- Action labels
- Metadata row labels
- Subtitle composition
- Fallback labels

Once the BFF emits pre-composed strings, the frontend no longer has enough information to re-translate them. The semantic key is gone. Therefore:

- The BFF accepts locale input via `Accept-Language` header.
- The BFF resolves all API-delivered display labels in the requested locale.
- The frontend only translates UI strings that never come from the API.

**Principle: If the BFF sends display-ready strings, the BFF must own locale-aware composition.**

### Start with German as baseline

The current state (English labels with `lang="de"`) is a correctness bug. Phase 0 converts all hardcoded English labels to German before introducing multi-locale infrastructure.

**Principle: Fix the default language experience first, then generalize.**

### Multi-language document variants are not i18n

Swiss legal materials may exist in multiple official language variants. This is a content-modeling concern, not a UI-locale concern. When supported:

- Translated or alternate content variants should be modeled as explicit document variants.
- They should be produced as persistent derived data by document-intelligence or an adjacent offline translation pipeline.
- They should be versioned and auditable.
- They should be clearly distinguished from the original legal text.

**Principle: Translated legal content is a content-variant problem, not an i18n problem.**

**Invariant: Any future document translation feature must be modeled as explicit derived content, versioned and clearly distinguished from the original legal text. The original text remains the source of truth for reasoning, citation, and legal interpretation.**

## Non-Goals

- **Machine-translating document content at runtime.** Legal content must be served in its original language. Translation, if offered, is a separate pipeline concern.
- **Platform-control i18n.** Platform-control is an internal ops tool — not user-facing. i18n is not a priority for it.
- **Right-to-left (RTL) support.** The target languages (German, French, Italian) are all LTR.
- **Per-language OpenSearch analyzers (Phase 1).** Language-specific search quality improvements (German compound-word splitting, French accent handling) are a search-quality concern for later phases, not part of the initial i18n rollout.

## Component Responsibilities

| Component | i18n Responsibility |
|-----------|-------------------|
| **Contracts / Vocabularies** | Carry locale-keyed labels for domain terms (jurisdictions, document types) |
| **Document-Intelligence** | Detect and assign `language` field. No UI locale awareness |
| **OpenSearch** | Store `language` as keyword field. No locale-specific behavior in Phase 1 |
| **BFF (NestJS)** | Accept `Accept-Language`, resolve all composed labels in requested locale |
| **Frontend (Next.js)** | `next-intl` for UI chrome that does not come from the API |
| **Platform-Control** | None |

### What the frontend translates

| Category | Examples |
|----------|---------|
| App shell | Title, header text |
| Search input | Placeholder text |
| Tray labels | "Trail", "Pinned" |
| Empty states | "No related materials", "No annotations available" |
| Interactive labels | "Pin"/"Unpin", "Copy citation", "Show all", "Back" |
| Command palette | Title and placeholder |

### What the frontend does NOT translate

| Category | Why |
|----------|-----|
| Badge labels | Come from BFF, already localized |
| Facet labels | Come from BFF |
| Action labels | Come from BFF |
| Tab labels | Come from BFF |
| Metadata row labels | Come from BFF |
| Document content | Content language — never translated |

## Phased Rollout

| Phase | Scope | Components |
|-------|-------|-----------|
| **0 — Fix labels to German** | Convert all English labels in mappers and vocabularies to German | BFF mappers, vocabulary files |
| **1 — BFF i18n infrastructure** | `Accept-Language` parsing, locale-aware vocabulary loader, BFF translation files, mapper refactor | BFF |
| **2 — Frontend i18n** | `next-intl` setup, `[locale]` routing, extract component strings, `de.json` | Frontend |
| **3 — French** | `fr.json` for frontend + BFF, vocabulary `labels.fr` | All |
| **4 — OpenSearch analyzers** | Per-language sub-fields, query routing for search quality | OpenSearch, BFF adapter |
| **5 — Italian** | Add `it` following the same pattern as French | All |

## Risks

| Risk | Mitigation |
|------|-----------|
| BFF label composition becomes complex with locale threading | Keep mappers as pure functions; locale is just another parameter |
| Vocabulary label translations become stale | Vocabulary changes already require PR review (ADR-0012). Add locale labels to the review checklist |
| Frontend and BFF translations diverge (same concept, different label) | **The ownership boundary alone was not enough — this risk materialised.** The boundary says which surface *emits* a label, not which word it uses, and the frontend has to write prose about the things the BFF labels. By 2026-09 the detail panel's tab strip read "Zitationen" (BFF) directly above a heading reading "Verweise" (frontend), with "Referenzen" (BFF) between them. Now enforced: `legal-search/api/src/core/i18n/terminology.ts` is the single source of truth for words that appear on both surfaces, and `terminology.spec.ts` is the single check — it reads *both* surfaces' message files and fails on disagreement. A copy of the check in each surface would be the same defect again |
| New vocabulary values added without locale labels | Extend vocabulary contract spec tests to require `labels` for all supported locales |
| Text expansion (German ~30% longer than English) breaks layouts | Already mitigated: the primary locale is German, which is typically the longest |

## Consequences

- **Vocabulary files** gain a `labels` map alongside the existing `label` field. The `label` field remains as the English fallback and canonical reference label.
- **BFF mappers** accept a `locale` parameter. All composed display strings are resolved in that locale.
- **BFF controllers** parse `Accept-Language` and pass locale through to services and mappers.
- **Frontend** uses `next-intl` with `[locale]` App Router routing. Only translates strings not delivered by the API.
- **OpenAPI spec** documents `Accept-Language` as an optional header on all operations.
- **Adding a new supported locale** requires: vocabulary `labels` entries, BFF translation file, frontend translation file. No schema or API contract changes.
- **Adding a new vocabulary value** (ADR-0012) now also requires providing labels for all supported locales.

## Rationale

### Why not translate everything in the frontend?

The BFF already composes display-ready strings. If the frontend received raw keys instead, it would need to replicate all the BFF's composition logic (badge rules, subtitle assembly, facet grouping, action config). This violates the BFF's purpose as the composition layer.

### Why not translate everything in the BFF?

The BFF should not own strings it never composes. UI-only chrome (empty states, input placeholders, interactive labels) is a frontend concern. The BFF has no business knowing what the "Pin" button says.

### Why vocabulary files and not a separate translation service?

The vocabulary set is small (4 jurisdictions, 4 document types), domain-specific, and already loaded by the BFF at startup. A translation service or database would be over-engineering. If the vocabulary grows significantly, this decision can be revisited.

### Why `next-intl` over `react-i18next`?

`next-intl` is purpose-built for the Next.js App Router, supports server components natively, has built-in ICU MessageFormat for plurals, and weighs ~2KB on the client vs ~12KB for `react-i18next`. The project already uses Next.js 16 with the App Router.
