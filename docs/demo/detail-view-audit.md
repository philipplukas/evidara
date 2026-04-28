# Detail-view trust-signal audit (template)

Owner: Demo lead
Last reviewed: 2026-04-28
Status: **Audit template** — execute against prod for each of the 12 corpus documents before the demo. The checklist below is grounded in what the contract and the BFF mapper actually surface today; it is not aspirational.

## Why this audit exists

The internal-beta evidence packet ([`internal-beta-user-flow-evidence.md:54`](../runbooks/internal-beta-user-flow-evidence.md)) asserts a *corpus-level* minimum: ≥4 metadata rows, controlled `law` type, content/sections/citations/details tabs (the runbook's English tab labels — the live UI uses German per ADR-0013). A demo audience reads *one* document end-to-end. This audit is the per-document QA pass that the corpus-level check does not cover.

Goal: **before demo day, every document referenced in [`demo/script.md`](script.md) passes this checklist.** Documents not referenced by the script can pass post-demo.

## What the contract guarantees (do not invent extra fields)

From [`contracts/api/legal-search.openapi.yaml`](../../contracts/api/legal-search.openapi.yaml) `DetailView` (lines 493–547):

| Field | Required? | Notes |
|---|---|---|
| `id`, `type`, `title`, `subtitle` | required | `title`/`subtitle` may be empty strings; the frontend falls back to `t("fallbackTitle")` / `t("fallbackSubtitle")` ([DetailPanelHeader.tsx:22](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx)) |
| `breadcrumbs` | optional array | Rendered above the title when present |
| `metadata` | required (default `[]`) | Composed by [`document-detail.mapper.ts`](../../legal-search/api/src/modules/documents/mappers/document-detail.mapper.ts) — see "Metadata composed by the BFF" below |
| `content` | optional object | DoclingDocument JSON, renders inside the `details` tab |
| `contentLanguage` | optional | Drives the translation badge (only shown when `isTranslation === true`) |
| `tabs` | required (default `[]`) | Live keys: `details`, `related`, `references`, `annotation`, `structure` ([DetailPanel.tsx:46–74](../../legal-search/frontend/src/components/detail/DetailPanel.tsx)) |
| `relatedGroups`, `references`, `annotations` | required (default `[]`) | Power the eponymous tabs |
| `localStructure` | optional | Powers the `structure` tab |

There is **no** `provenanceUrl` / `sourceUrl` / `fedlexUrl` field on `DetailView` today. The BFF mapper currently emits a `metadata.source` row whose value is a localized **label** (`"officialSource"`), not a hyperlink ([`document-detail.mapper.ts:163`](../../legal-search/api/src/modules/documents/mappers/document-detail.mapper.ts)). This is the single biggest trust gap for a credibility-sensitive audience and is called out in the post-audit recommendations below.

## Metadata rows composed by the BFF

The mapper assembles up to seven rows per document ([`document-detail.mapper.ts`](../../legal-search/api/src/modules/documents/mappers/document-detail.mapper.ts) ~lines 100–185, in order):

1. **Status** — e.g. `"In Kraft"` (in force)
2. **Date / In-force date** — `metadata.inForce` for laws, `metadata.date` for decisions
3. **Authority** — e.g. `auth_fedlex` resolved to its display label
4. **Citation** — e.g. `SR 754` (the SR number, distinct from the share-button citation copy)
5. **Source** — value `"officialSource"` (localized **label**, currently no URL)
6. **Jurisdiction** — e.g. Switzerland · Federal
7. **Language** — e.g. Deutsch / Französisch / Italienisch

Document type and label heuristics ([`metadata-icons.ts`](../../legal-search/api/src/core/presentation/metadata-icons.ts) referenced from the mapper) decide which rows are "always" / "default" / "expanded" visibility, then the frontend's `enrichMetadataRows` ([`metadata-visibility.ts`](../../legal-search/frontend/src/lib/metadata-visibility.ts)) makes the final cut by document `type`.

For a Swiss federal **law**, expect rows 1, 2, 3, 4, 6, 7 to be present (≥6 rows). Row 5 ("Source") is currently a label; it should still appear.

## The audit checklist

Run for each document referenced by [`script.md`](script.md). Treat any **❌** as a demo blocker for that document.

### A. Header (`DetailPanelHeader`)

| # | Check | Pass criterion | Source |
|---|---|---|---|
| A1 | Canonical title | Renders the actual title (e.g. "Bundesverfassung der Schweizerischen Eidgenossenschaft"); not the i18n fallback `detail.fallbackTitle` | [DetailPanelHeader.tsx:22](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |
| A2 | Subtitle | Composed string (e.g. "Schweiz · Bundesrecht"); not the fallback | [DetailPanelHeader.tsx:23](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |
| A3 | Breadcrumbs | Present when the BFF emits them; verify they render in DOM order | [DetailPanelHeader.tsx:33](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |
| A4 | Translation badge | Shows iff `contentLanguage.isTranslation === true`; original-language docs show no badge (this is correct) | [DetailPanelHeader.tsx:44](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |
| A5 | Compact metadata strip | When `detail.metadata.length > 0`, header renders a compact `MetadataList`; verify ≥4 visible rows | [DetailPanelHeader.tsx:50](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |
| A6 | Pin / share / print / copy-citation buttons | All four render and are keyboard-reachable; copy-citation writes `${title} - ${subtitle}` to clipboard | [DetailPanelHeader.tsx:61–91](../../legal-search/frontend/src/components/detail/DetailPanelHeader.tsx) |

### B. Tabs (`DetailPanel` + `DetailTabs`)

| # | Check | Pass criterion | Source |
|---|---|---|---|
| B1 | Tab keys present | At minimum `details` is present; for laws also `structure` and `references` typically populate | [DetailPanel.tsx:45](../../legal-search/frontend/src/components/detail/DetailPanel.tsx) |
| B2 | Default active tab | `details` opens by default and is keyboard-navigable | [DetailTabs.tsx](../../legal-search/frontend/src/components/detail/DetailTabs.tsx) |
| B3 | Tab counts | When present, counts (e.g. references count) match the actual tab body | `TabView.count` in OpenAPI |

### C. Details tab body (`DetailsTab`)

| # | Check | Pass criterion | Source |
|---|---|---|---|
| C1 | Document body renders | `contentHtml` (sanitized by DOMPurify) renders typeset body — no raw HTML, no broken markup | [DetailsTab.tsx:18–23](../../legal-search/frontend/src/components/detail/tabs/DetailsTab.tsx) |
| C2 | Heading hierarchy | At least one `h4` (article-level) is visible for laws; no orphan `<strong>` blocks | [DetailsTab.tsx:48–55](../../legal-search/frontend/src/components/detail/tabs/DetailsTab.tsx) |
| C3 | Empty-state guard | If `contentHtml` is absent, the empty-state copy appears instead of a blank pane | [DetailsTab.tsx:61](../../legal-search/frontend/src/components/detail/tabs/DetailsTab.tsx) |
| C4 | Full metadata list | Repeated below the body in `default` density, showing all the BFF-composed rows | [DetailsTab.tsx:37–42](../../legal-search/frontend/src/components/detail/tabs/DetailsTab.tsx) |

### D. Other tabs (validate they don't render placeholder)

| # | Check | Pass criterion |
|---|---|---|
| D1 | `structure` tab | If present in `tabs`, opens to the table of contents; `localStructure.items` is non-empty |
| D2 | `references` tab | If present, renders ≥1 reference group; no group is labelled "TODO" / "—" |
| D3 | `related` tab | If present, renders ≥1 related-doc card; if the corpus has only 12 docs, "no related found" copy is acceptable but should not look broken |
| D4 | `annotation` tab | Either renders annotations or shows the `TabEmptyState` copy — never a blank pane |

## Per-document audit table (fill in before T-7)

Copy this row 12 times — once per corpus document from [`internal-beta-user-flow-evidence.md:23`](../runbooks/internal-beta-user-flow-evidence.md). Mark each cell ✅ / ❌ / N/A.

| Doc ID | A1 | A2 | A4 | A5 | A6 | B1 | B2 | C1 | C2 | C4 | D1 | D2 | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `doc_6vfta1cd5xy642g7eb59j8wkfm` (BV) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_67b9202dsxm52sa36dsfvcm6bt` (OR) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_20djzpnf2yytwg9k74zyzjdeta` (ZPO) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_2em3ky37mw9tm7hxh5nkw0zkh7` (FADP) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_2adkyv1qccx2pg3mqa7d233s0y` (ZGB) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_30hr7xpm9ptmmanpbydwpxdv61` (StGB) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_4n4nh4khmzfxh3hdshpvw6x4mp` (StPO) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_6mej0nyg3qfenw0zbdmhtq6cmn` (SchKG) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_4pqxtsmegg44t5zg3es8d27b4v` (VwVG) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_1f0vr4pdkn9havmnws60mb9n6y` (BGG) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_3vyh663grb4kwyb96x4sd8xb1f` (IPRG) |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `doc_1jyt8vad5ed2p294t31ctj53dw` (KG) |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Recommendations (post-audit, expected)

These are the changes most likely to be triggered by running the audit. Listed so the demo team can pre-allocate engineering capacity.

1. **No clickable provenance URL.** Mitigation options for a 2-week demo, in order of preference:
   - **Talk-track only.** Presenter says "this is sourced from Fedlex; we'll show the link in the next iteration." Cheapest. No code change.
   - **Surface a hardcoded `fedlex.admin.ch/eli/cc/<sr>` link in the metadata row.** Requires a small BFF mapper change to push a URL through `metadata.source` (would also need a `MetadataRow.href` field — contract change). Avoid in 2-week window.
   - **Skip.** Acceptable for an investor audience; risky for a strategic-partner audience.
2. **Empty subtitle / fallback title** — fix at the source-data level if any document hits the fallback. Not a code change; a content-correctness change.
3. **`structure` or `references` tab empty for a law** — investigate whether `localStructure` is populated; if not, hide the tab key for that document via the BFF rather than show an empty pane.

## How to run the audit

1. Open prod legal-search in two browsers (Chrome + Safari) — Safari catches DOMPurify edge cases.
2. For each doc ID above:
   - Search by SR number (e.g. `SR 754`) or by title fragment.
   - Open detail; tick A1–A6 in the header.
   - Cycle through tabs B1–B3 / C1–C4 / D1–D4.
   - Note any ❌ in the per-document row.
3. Triage ❌ rows: blocker (referenced by [`script.md`](script.md)) vs deferrable.
4. Re-run the smoke ([`demo-queries.spec.ts`](../../legal-search/frontend/e2e/demo-queries.spec.ts)) after any fix lands.

## Out of scope for this audit

- Search ranking quality — covered by [`demo-queries.spec.ts`](../../legal-search/frontend/e2e/demo-queries.spec.ts) and the smoke runbooks
- Visual regression — covered by `legal-search/frontend/e2e/visual.spec.ts`
- Accessibility — covered by [#484](https://github.com/philipplukas/evidara/pull/484) (axe a11y)
- Contracts / wire-level field changes — explicitly anti-scope per the demo plan
