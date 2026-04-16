# Design System

> Visual language, tokens, typography, and CSS patterns for Evidara Legal Search.

---

## Token Architecture

All colors are defined as CSS custom properties in `[globals.css](../src/app/globals.css)` and exposed to Tailwind via `@theme inline`. Components never use hardcoded hex — they reference semantic tokens.

### Brand Tokens


| Token            | Value     | Tailwind Classes                             |
| ---------------- | --------- | -------------------------------------------- |
| `--brand`        | `#2563eb` | `text-brand`, `bg-brand`, `border-brand`     |
| `--brand-hover`  | `#1d4ed8` | `text-brand-hover`, `hover:text-brand-hover` |
| `--brand-strong` | `#1a2332` | `bg-brand-strong`, `text-brand-strong`       |


### Surface Tokens


| Token             | Value     | Tailwind Class     | Usage                         |
| ----------------- | --------- | ------------------ | ----------------------------- |
| `--surface-page`  | `#fafafa` | `bg-surface-page`  | Workspace shell, mobile shell |
| `--surface-panel` | `#ffffff` | `bg-surface-panel` | Panels, cards, sheets, header |
| `--surface-input` | `#f8f9fa` | `bg-surface-input` | Search input background       |


### Interactive Tokens


| Token                         | Value       | Tailwind Class                 | Usage                                     |
| ----------------------------- | ----------- | ------------------------------ | ----------------------------------------- |
| `--interactive-accent-subtle` | brand @ 5%  | `bg-interactive-accent-subtle` | Hover backgrounds, active ContextBar tabs |
| `--interactive-accent-muted`  | brand @ 10% | `bg-interactive-accent-muted`  | Active pin button, nav badge pill         |
| `--focus-ring`                | brand @ 20% | `focus:ring-focus-ring`        | Input focus rings                         |


### Tab tokens (Radix `line` variant)


| Token                      | Light          | Dark                | Usage                                                                             |
| -------------------------- | -------------- | ------------------- | --------------------------------------------------------------------------------- |
| `--tab-indicator-color`    | `var(--brand)` | `var(--foreground)` | Active tab underline / vertical rail (`tabs.tsx` `after:`)                        |
| `--tab-active-font-weight` | `700`          | (inherits)          | Detail tabs active weight (`DetailTabs` + `font-[var(--tab-active-font-weight)]`) |


### shadcn Semantic Tokens

Inherited from the shadcn theme and used as-is:


| Token                | Tailwind Class          | Purpose                                        |
| -------------------- | ----------------------- | ---------------------------------------------- |
| `--muted`            | `bg-muted`              | Inactive chip/button backgrounds, hover states |
| `--muted-foreground` | `text-muted-foreground` | Secondary text, labels, metadata               |
| `--border`           | `border-border`         | All structural borders                         |
| `--foreground`       | `text-foreground`       | Primary text                                   |
| `--background`       | `bg-background`         | Base page background                           |


---

## Typography

### Font Stack


| Variable       | Family         | Weights  | Role                                               |
| -------------- | -------------- | -------- | -------------------------------------------------- |
| `--font-inter` | Inter          | 400–700  | All UI text (headings, labels, buttons, metadata)  |
| `--font-serif` | Source Serif 4 | 400, 600 | Legal content — snippets, annotations, detail HTML |


Body font set via `--font-inter` on `<body>`. Legal content areas use the `.font-document` utility class defined in `globals.css`:

```css
.font-document {
  font-family: var(--font-serif), "Georgia", serif;
}
```

### Type Scale (5 sizes + 2 display)


| Token        | Size | Tailwind            | Usage                                                                  |
| ------------ | ---- | ------------------- | ---------------------------------------------------------------------- |
| `text-lg`    | 18px | built-in            | Wordmark only                                                          |
| `text-base`  | 16px | built-in            | Detail title                                                           |
| `text-sm`    | 14px | built-in            | Result titles, content text, search input                              |
| `text-xs`    | 12px | built-in            | Labels, metadata, tabs, filter labels                                  |
| `text-micro` | 11px | `--font-size-micro` | Actions, structural context, breadcrumbs, AccentButton, ActionTextLink |
| `text-tiny`  | 10px | `--font-size-tiny`  | Badge labels, counts, micro pills                                      |


Both `text-micro` and `text-tiny` are registered as custom Tailwind font-size tokens in `@theme inline`.

### Font Weights


| Class           | Weight | Usage                                         |
| --------------- | ------ | --------------------------------------------- |
| `font-bold`     | 700    | Wordmark "E"                                  |
| `font-semibold` | 600    | Titles, active items, section headers, badges |
| `font-medium`   | 500    | Labels, buttons, chip text                    |
| `font-normal`   | 400    | Body text, counts                             |


---

## Primitives

Reusable design components in `[src/components/primitives/](../src/components/primitives/)`. All primitives use design tokens — no hardcoded hex.

**Barrel exports:** see `[primitives/README.md](../src/components/primitives/README.md)` for the authoritative export list (`TAR-267`).

### SectionLabel

Consistent section header. Replaces the repeated `text-xs font-semibold uppercase tracking-wider text-muted-foreground` pattern.

```tsx
<SectionLabel>Related Documents</SectionLabel>
```

**Used by:** DetailsTab, RelatedTab, ReferencesTab, StructureTab, FilterPanel

### InteractiveRow

Clickable preview row with hover state. Replaces the repeated `flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/50 cursor-pointer transition-colors` pattern.

```tsx
<InteractiveRow onClick={handleClick}>
  <span>{title}</span>
</InteractiveRow>
```

**Used by:** RelatedTab, ReferencesTab

### AccentButton

Small action button with active/inactive states. Uses `text-micro` size.

```tsx
<AccentButton active={isPinned} onClick={handlePin} title="Pin">
  <Pin className="w-3 h-3" />
</AccentButton>
```

- **Active:** `text-brand bg-interactive-accent-muted`
- **Inactive:** `text-muted-foreground hover:text-brand hover:bg-interactive-accent-subtle`

**Used by:** DetailPanelHeader, ResultCard

### ActionTextLink

Small accent text link for navigation actions. Uses `text-micro` size.

```tsx
<ActionTextLink onClick={handleShowAll} showArrow>
  Show all
</ActionTextLink>
```

**Used by:** RelatedTab, ReferencesTab, ResultSetScopeBar

### Badge

Colored document-type pill using the generic palette from `[badge-tokens.ts](../src/lib/badge-tokens.ts)`.

```tsx
<Badge label="Gesetz" colorKey="blue" />
<Badge label="Entscheidung" colorKey="pink" size="xs" />
```

The `colorKey` is assigned by the BFF — the UI has no knowledge of document type → color mapping.

**Palette:** blue, pink, indigo, green, amber, slate (+ gray fallback)
**Sizes:** `sm` (default) and `xs` (preview surfaces)

**Used by:** ResultCard, ExactMatchStrip, RelatedTab

---

## Badge Color Palette

Defined in `[src/lib/badge-tokens.ts](../src/lib/badge-tokens.ts)`. The keys are visual, not semantic:


| Key      | Background | Text      |
| -------- | ---------- | --------- |
| `blue`   | `#dbeafe`  | `#1e40af` |
| `pink`   | `#fce7f3`  | `#9d174d` |
| `indigo` | `#e0e7ff`  | `#3730a3` |
| `green`  | `#d1fae5`  | `#065f46` |
| `amber`  | `#fef3c7`  | `#92400e` |
| `slate`  | `#f1f5f9`  | `#334155` |
| fallback | `#f3f4f6`  | `#374151` |


## Pill / Badge contract (cross-surface, TAR-243 / ADR-0016)

Three pill families exist across the two surfaces. They must not be mixed; pick the family that matches the *meaning* of the pill, not the visual preference.

| Family | When to use | legal-search | admin | Shared tokens |
| ------ | ----------- | ------------ | ----- | ------------- |
| **Domain colour badge** | Document type (Law, Decision, Commentary) — categorical, brand-assigned colour | `<Badge label="…" colorKey="pink" />` (`[primitives/Badge.tsx](../src/components/primitives/Badge.tsx)`) | Not used (admin does not surface document type) | Palette from `[badge-tokens.ts](../src/lib/badge-tokens.ts)` (visual, not semantic) |
| **Semantic status badge** | Lifecycle state (Active, Blocked, Pending, Failed) | `<StatusBadge level="healthy" label="Active" />` (`[primitives/StatusBadge.tsx](../src/components/primitives/StatusBadge.tsx)`) | `<StatusBadge level="healthy" label="Active" />` (MUI `Chip`, admin `resources/shared/StatusBadge.tsx`) | Shared `StatusLevel` vocabulary — see [admin status-level table](../../../platform-control/admin/docs/status-level-vocabulary.md) |
| **Neutral metadata chip** | Filter chip, jurisdiction label, version stamp | `.context-bar__chip` / `.context-bar__chip--active` / `.context-bar__chip--idle` | MUI `<Chip variant="outlined" size="small" />` | Rounded-full pill, 11px text, neutral palette |

**Usage rules**

- **Never** use the domain colour badge to encode status. Status is `StatusLevel` + icon + label (WCAG 1.4.1).
- Prefer the shared primitive over a one-off span. Introducing a fourth family requires an ADR.
- Visual contract for the neutral metadata chip (family 3): `borderRadius: 999` (full pill), 11px text, weight 600, 24px height at `size="small"`. The admin MUI `MuiChip` theme mirrors the Tailwind `.context-bar__chip` values so the two surfaces read as one family.

### Special Context Colors

These use Tailwind's built-in color palette (not tokens) for domain-specific badges:


| Element           | Classes                           | Usage                          |
| ----------------- | --------------------------------- | ------------------------------ |
| Translation badge | `bg-amber-50 text-amber-700`      | Machine translation indicator  |
| Confidence badge  | `bg-green-50 text-green-700`      | AI annotation confidence       |
| Annotation card   | `border-brand/10 bg-brand/[0.02]` | AI/editorial annotation panels |


---

## Spacing & Layout

### Border Radius


| Token             | Value                       |
| ----------------- | --------------------------- |
| `--radius` (base) | `0.625rem` (10px)           |
| Buttons/inputs    | `rounded-lg` / `rounded-md` |
| Chips             | `rounded-full`              |
| Badges            | `rounded` (4px)             |


### Common Padding Patterns


| Element            | Padding     |
| ------------------ | ----------- |
| Header             | `px-6 py-3` |
| Context bar        | `px-6 py-2` |
| Filter group body  | `px-4 pb-3` |
| Result card        | `px-5 py-4` |
| Detail header      | `px-5 py-4` |
| Detail tab content | `p-5`       |


---

## Elevation & shadows

Structural depth uses **named CSS variables** in `[globals.css](../src/app/globals.css)` (not ad-hoc `shadow-lg` on chrome):


| Token                    | Typical use                                                         |
| ------------------------ | ------------------------------------------------------------------- |
| `--shadow-shell`         | Sticky app header (`box-shadow: var(--shadow-shell)`)               |
| `--shadow-control-plane` | Floating control surfaces (e.g. elevated panels tied to brand tint) |


**Rule:** new floating surfaces pick a **named** token or add one with design review; avoid one-off `box-shadow` unless documented here (`TAR-246`, `TAR-261`).

---

## Border hierarchy


| Kind                    | Classes / token                                     | When                                                                    |
| ----------------------- | --------------------------------------------------- | ----------------------------------------------------------------------- |
| Structural dividers     | `border-border` or `border-border/60`–`/70`         | Panel edges, header/footer separators — softer opacity = lower emphasis |
| Input / control outline | `border-border/70` + `focus:border-brand`           | Search field, form controls                                             |
| Selection emphasis      | `border-l-2 border-l-brand` (transparent when idle) | Result list selection, structure nav current item                       |
| Dashed empty            | `border-dashed border-border/70`                    | Empty metadata placeholder                                              |


---

## Interactive Patterns

### Transitions


| Pattern         | CSS                    | Duration      | Used on               |
| --------------- | ---------------------- | ------------- | --------------------- |
| Color swap      | `transition-colors`    | 150ms default | Buttons, links, chips |
| All properties  | `transition-all`       | 150ms default | Chips, toggles, cards |
| Opacity reveal  | `transition-opacity`   | 150ms default | Action bar hover      |
| Transform slide | `transition-transform` | 150ms default | Toggle switch thumb   |


### Selection States


| Element                   | Selected                                                                                                       | Unselected                                                              |
| ------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Result card               | `bg-brand/[0.03] border-l-2 border-l-brand`                                                                    | `hover:bg-muted/30 border-l-2 border-l-transparent`                     |
| Detail tab (Radix `line`) | `font-[var(--tab-active-font-weight)] text-foreground` + bottom `after:` bar `bg-[var(--tab-indicator-color)]` | `font-medium text-muted-foreground/70` + indicator hidden (`opacity-0`) |
| Structure item            | `bg-interactive-accent-subtle text-brand border-l-2 border-l-brand`                                            | `text-foreground/70 hover:bg-muted/50`                                  |
| Chip (ContextBar)         | `bg-brand-strong text-white shadow-sm`                                                                         | `bg-muted text-muted-foreground`                                        |
| Tab (ContextBar)          | `text-brand bg-interactive-accent-subtle`                                                                      | `text-muted-foreground hover:bg-muted`                                  |
| Pin button                | `text-brand bg-interactive-accent-muted` (via AccentButton)                                                    | `text-muted-foreground` (via AccentButton)                              |


### Focus States


| Element       | Ring                     | Border         |
| ------------- | ------------------------ | -------------- |
| Search input  | `ring-2 ring-focus-ring` | `border-brand` |
| Filter search | `ring-1 ring-focus-ring` | —              |
| Resize handle | `ring-1 ring-ring`       | —              |


### Hover Reveal

Action buttons on `ResultCard` use `opacity-0 group-hover:opacity-100 transition-opacity` — invisible until the card is hovered.

---

## Icon System

### Lucide Icons (react)

All icons from `lucide-react`. Standard size: `w-3 h-3` to `w-4 h-4`.

### Emoji Flag Registry

Country/canton flags use emoji via `[icons.ts](../src/lib/icons.ts)`:


| Key     | Emoji | Display       |
| ------- | ----- | ------------- |
| `ch`    | 🇨🇭  | Switzerland   |
| `at`    | 🇦🇹  | Austria       |
| `ch-zh` | `ZH`  | Zürich (text) |
| `ch-be` | `BE`  | Bern (text)   |
| ...     | ...   | Other cantons |


Production milestone: replace with SVG flag components or `circle-flags` library.

---

## Search controls IA (ADR-0016 Contracts 1–2, TAR-255 / TAR-256)

**Goal:** Users always know *where* they narrow results vs *which* corpus they search. Nothing should mutate the result list except controls inside the bounded results region.


| Zone                            | Component                                                                                                                                   | Owns                                                                                                                       | Dispatches via                                                                                                 |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Global / corpus constraints** | `[ContextBar](../src/components/layout/ContextBar.tsx)`                                                                                     | Jurisdiction, language, source-type tabs, official-only toggle                                                             | `SearchConstraintsProvider` (`TOGGLE_JURISDICTION`, `TOGGLE_LANGUAGE`, `SET_SOURCE_TYPE`, `SET_OFFICIAL_ONLY`) |
| **Refinement filters**          | `[FilterPanel](../src/components/filters/FilterPanel.tsx)` (desktop) / `[FiltersSheet](../src/components/layout/FiltersSheet.tsx)` (mobile) | Facet groups, filter search; delegates active chips to `[FilterBar](../src/components/filters/FilterBar.tsx)`              | Same provider (`SET_FILTER`, `CLEAR_FILTERS`, …)                                                               |
| **Results control region**      | `[ResultsControlRegion](../src/components/results/ResultsControlRegion.tsx)`                                                                | Visual grouping + landmark for “everything that changes the current hit list” (scope bar, exact-match strip, `ResultList`) | Wraps children only; individual children dispatch                                                              |


**Invariant:** Facet-driven refinements and list-scoping actions (pivot, back) surface in the results column — `FilterBar` chips are shared between desktop panel and mobile sheet so clear-all and per-chip dismiss stay consistent.

### Inside `ResultsControlRegion` (must be children)

- `ResultSetScopeBar` — back/pivot breadcrumb for the current result set
- `ExactMatchStrip` / `ResultContextHeader` — exact-match results
- `ResultList` — the hit list itself

### Outside `ResultsControlRegion` (must NOT be children)

- `ContextBar` — corpus-level constraints (jurisdiction, language, source type, official-only toggle); these set the *search universe*, not narrow the current hit list
- `FilterPanel` / `FiltersSheet` — facet refinement groups; rendered in the left column (desktop) or bottom sheet (mobile), adjacent to but outside the region
- `AppHeader` — search input, navigation, control-plane link
- `DetailPanel` / `DetailSheet` — document detail; consumes selections from the result list

Both `WorkspaceClient` (desktop) and `MobileWorkspace` (mobile) wrap the same set of children inside `ResultsControlRegion`, preserving layout parity.

---

## Elevation

Named elevation tokens in `[globals.css](../src/app/globals.css)` (`:root` and `.dark`):


| Token                    | Purpose                                   | Light value                            |
| ------------------------ | ----------------------------------------- | -------------------------------------- |
| `--shadow-shell`         | App header and top-level workspace chrome | `0 18px 56px rgb(15 23 42 / 8%)`       |
| `--shadow-control-plane` | Control-plane link highlight              | `0 18px 40px rgb(15 76 129 / 18%)`     |
| `--shadow-panel`         | Primary content panels (results column)   | `0 20px 48px rgb(15 23 42 / 8%)`       |
| `--shadow-raised`        | Secondary panels (filters, detail)        | `0 16px 36px rgb(15 23 42 / 6%)`       |
| `--shadow-inset-surface` | Glass-highlight inset on cards and groups | `inset 0 1px 0 rgb(255 255 255 / 55%)` |
| `--shadow-sheet-top`     | Mobile bottom sheet upward shadow         | `0 -12px 40px rgb(15 23 42 / 6%)`      |


Use `shadow-[--shadow-*]` in Tailwind or `box-shadow: var(--shadow-*)` in CSS. Avoid arbitrary `shadow-[...]` with raw rgba values.

---

## Motion

Named motion tokens in `[globals.css](../src/app/globals.css)` (`:root` and `.dark`):


| Token                      | Value                          | When to use                         |
| -------------------------- | ------------------------------ | ----------------------------------- |
| `--motion-duration-short`  | `150ms`                        | Overlays, fades, micro-interactions |
| `--motion-duration-medium` | `200ms`                        | Sheets, panels, expand/collapse     |
| `--motion-easing-standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | All standard transitions            |


Utility classes: `.transition-motion-short`, `.transition-motion-medium` (set both duration and easing). `.transition-expand` for accordion-style open/close.

---

## Focus rings

Standard focus pattern: `focus-visible:ring-2 focus-visible:ring-focus-ring`. The `--focus-ring` token is `rgb(15 76 129 / 24%)` light, `rgb(74 158 218 / 30%)` dark.

Rules:

- Always use `focus-visible:` (not `focus:`) for keyboard-only focus indication.
- Always use `ring-2` width for consistency.
- Always use `ring-focus-ring` (not `ring-ring`, `ring-brand`, or arbitrary ring colors).
- For container focus (e.g. `ResultCard`), use `focus-within:ring-2 focus-within:ring-focus-ring`.

**Cross-surface parity:** the admin MUI surface uses `outline: 2px solid rgba(15, 76, 129, 0.24)` with `outlineOffset: 2` in `GlobalStyles` plus matching `MuiButton` / `MuiListItemButton` theme overrides (`[AdminApp.tsx](../../../platform-control/admin/src/app/AdminApp.tsx)`) to render the same visual as Tailwind `ring-2 ring-focus-ring`. If you introduce a new interactive element on either surface, reuse these exact values — do not substitute another opacity or width.

---

## Future Work

- **Dark Mode:** Brand/surface/interactive tokens have `.dark {}` overrides; keep auditing contrast and focus parity (`TAR-252`)
- **Docling Renderer Migration:** Replace HTML-string rendering in `DetailsTab.tsx` with structured Docling components when the BFF returns canonical document blocks

## Metadata visibility contract (TAR-258 decision)

**Target:** BFF-owned `visibility` on `MetadataRow` — the BFF is the canonical composition layer (see ADR-0011).

**Current:** The OpenAPI contract defines `MetadataRow.visibility` as optional (`always | default | expanded`). When the BFF sends it, the frontend uses it directly. When omitted, `metadata-visibility.ts` derives visibility from `label` + `documentType` heuristics.

**Why keep both paths:**

- The BFF progressively adopts `visibility` as document-type knowledge grows.
- The frontend heuristic is a safe fallback for fields the BFF hasn't classified yet.
- No contract or codegen changes are needed — the current optional-field design supports progressive adoption.

**Next step:** As the BFF mapper (`document-detail.mapper.ts`) gains per-document-type rules, it should populate `visibility` for all metadata rows. Once coverage is >95%, the frontend heuristic can be deprecated.

## Remaining (tracked in Linear)

Epic **[TAR-243](https://linear.app/tart-baozi/issue/TAR-243)** / project **[Evidara — Design system & UX (ADR-0016)](https://linear.app/tart-baozi/project/evidara-design-system-and-ux-adr-0016-8d1ece16235c)**. Detail tab line variant uses `--tab-indicator-color` and `--tab-active-font-weight` (`TAR-254` done). Cross-surface status vocabulary: [admin status-level table](../../../platform-control/admin/docs/status-level-vocabulary.md) (`TAR-251`).

**ADR:** [ADR-0016](../../../docs/adr/adr-0016-design-system-component-contracts.md) (**accepted** — component contracts are team guidance).