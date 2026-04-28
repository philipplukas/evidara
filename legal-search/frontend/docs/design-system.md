# Design System

> Visual language, tokens, typography, and CSS patterns for Evidara Legal Search.

---

## Token Architecture

All colors are defined as CSS custom properties in `[globals.css](../src/app/globals.css)` and exposed to Tailwind via `@theme inline`. Components never use hardcoded hex — they reference semantic tokens.

### Brand Tokens


| Token            | Value     | Tailwind Classes                             |
| ---------------- | --------- | -------------------------------------------- |
| `--brand`        | `#0f4c81` | `text-brand`, `bg-brand`, `border-brand`     |
| `--brand-hover`  | `#0b3d68` | `text-brand-hover`, `hover:text-brand-hover` |
| `--brand-strong` | `#1d293d` | `bg-brand-strong`, `text-brand-strong`       |


### Surface Tokens


| Token                     | Value / source | Tailwind Class              | Usage                         |
| ------------------------- | -------------- | --------------------------- | ----------------------------- |
| `--surface-page`          | `#e4e9ef`      | `bg-surface-page`           | Workspace shell, mobile shell |
| `--surface-panel`         | `#f8fafc`      | `bg-surface-panel`          | Panels, cards, sheets, header |
| `--surface-input`         | `#f1f5f9`      | `bg-surface-input`          | Search input background       |
| `--surface-shell`         | shared token   | `bg-surface-shell`          | Header/chip shell surfaces    |
| `--surface-shell-strong`  | shared token   | `bg-surface-shell-strong`   | Emphasized shell surfaces     |


### Interactive Tokens


| Token                         | Value       | Tailwind Class                 | Usage                                     |
| ----------------------------- | ----------- | ------------------------------ | ----------------------------------------- |
| `--interactive-accent-subtle` | brand @ 5%  | `bg-interactive-accent-subtle` | Hover backgrounds, active ContextBar tabs |
| `--interactive-accent-muted`  | brand @ 10% | `bg-interactive-accent-muted`  | Active pin button, nav badge pill         |
| `--focus-ring`                | brand @ 20% | `focus:ring-focus-ring`        | Input focus rings                         |


### Tab tokens (Radix `line` variant)


| Token                      | Light          | Dark                | Usage                                                                             |
| -------------------------- | -------------- | ------------------- | --------------------------------------------------------------------------------- |
| `--tab-indicator-color`    | `var(--brand)` | `var(--foreground)` | Active tab underline / vertical rail (`tabs.tsx` `after:`) — kept at `--brand` for non-detail tabs; detail tabs override inline to `--accent-core` per Sprint 1 |
| `--tab-active-font-weight` | `700`          | (inherits)          | Detail tabs active weight (`DetailTabs` + `font-[var(--tab-active-font-weight)]`) |


### Accent-core token family (Sprint 1 — TAR-244)

The Evidara violet accent — used wherever the UI needs to **signal an action or transient state** on non-destructive elements (primary actions, active tab, active filter, count badge). Never use it for destructive state (that's `--destructive`) or for identity-only chrome (that's navy `--brand`).

| Token | Value | Tailwind Class | Usage |
|-------|-------|----------------|-------|
| `--accent-core` | `oklch(0.55 0.24 285)` ≈ `#7c3aed` | `text-accent-core`, `bg-accent-core`, `border-accent-core` | Active detail-tab indicator, active tab count badge foreground, active ContextBar scope tab, active StructureTab item, active admin nav item (`Mui-selected`) |
| `--accent-core-foreground` | `oklch(0.985 0 0)` | `text-accent-core-foreground` | Text on top of filled accent surfaces |
| `--accent-core-subtle` | accent-core @ 14 % | `bg-accent-core-subtle` | Tinted active backgrounds (count badges, active pill fill) |
| `--accent-core-muted` | accent-core @ 22 % | `bg-accent-core-muted` | Active-hover, selected-hover |

**Cross-surface parity:** the admin MUI theme mirrors these via `ACCENT_CORE`, `ACCENT_CORE_SUBTLE`, `ACCENT_CORE_MUTED` in `platform-control/admin/src/lib/admin/designTokens.ts`. Both surfaces apply accent-core to the same semantic states (active nav item, active tab, filter activation), so moving between legal-search and the control plane never re-teaches the user what "active" looks like.

### Shadow + elevation tokens (Sprint 1 — TAR-244)

Paired with a cooled `--surface-page` (`#e4e9ef` instead of `#eef2f6`) so cards actually lift off the page background.

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-card` | `0 1px 3px rgba(15,76,129,0.08), 0 1px 2px rgba(15,76,129,0.04)` | Resting state on elevated surfaces |
| `--shadow-card-hover` | `0 6px 18px rgba(15,76,129,0.10), 0 2px 6px rgba(15,76,129,0.06)` | Hover state — paired with a 180 ms transition |
| `--shadow-shell` | `0 18px 56px rgba(15,23,42,0.08)` | App header / shell |
| `--shadow-control-plane` | `0 18px 40px rgba(15,76,129,0.18)` | Control-plane CTA, admin AppBar |

A `.elevated-card` utility class (see `globals.css`) bundles `--shadow-card` + hover transition + `prefers-reduced-motion` fallback. Apply it to any standalone panel or tile that sits on `--surface-page`.

### Motion tokens (Sprint 1 — TAR-244)

Sprint 1's `.elevated-card` uses these existing design-system motion tokens so card hover stays in the same visual language as sheets and panels. See the "Motion" section below for the canonical table; Sprint 1 adds no new motion tokens, it only introduces the `.elevated-card` utility that consumes them.

Components MUST honour `prefers-reduced-motion: reduce` (the `.elevated-card` utility does this automatically).

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


| Element                         | Selected                                                                                              | Unselected                                          |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Result card                     | `bg-brand/[0.03] border-l-2 border-l-brand` (navy — the list's "focused row")                         | `hover:bg-muted/30 border-l-2 border-l-transparent` |
| Detail tab (Radix `line`)       | `data-[state=active]:border-accent-core data-[state=active]:text-accent-core` (accent — "active state") | `font-medium text-muted-foreground/70`              |
| Detail tab count badge          | `group-data-[state=active]:bg-accent-core-subtle group-data-[state=active]:text-accent-core`          | `bg-muted text-muted-foreground/70`                 |
| Structure item                  | `bg-accent-core-subtle text-accent-core border-l-2 border-l-accent-core`                              | `text-foreground/70 hover:bg-muted/50`              |
| Chip (ContextBar)               | `bg-brand-strong text-white shadow-sm` (navy — categorical, not transient state)                      | `bg-muted text-muted-foreground`                    |
| Tab (ContextBar)                | `text-accent-core bg-accent-core-subtle ring-1 ring-accent-core/15`                                   | `text-muted-foreground hover:bg-muted`              |
| Official-sources toggle         | `text-accent-core bg-accent-core-subtle border-accent-core/30`                                        | `text-muted-foreground`                             |
| Pin button                      | `text-brand bg-interactive-accent-muted` (via AccentButton — brand semantics, not state)              | `text-muted-foreground` (via AccentButton)          |
| Admin nav item (`Mui-selected`) | `backgroundColor: ACCENT_CORE_SUBTLE; color: ACCENT_CORE`                                             | `backgroundColor: transparent`                      |

**Colour semantics.** `--brand` marks *identity* (where you are, whose data you're looking at, which record is focused in a list). `--accent-core` marks *transient state* (is this tab active right now, is this filter switched on right now). Never collapse the two.


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

## Date formatting contract (Sprint 1 — TAR-244)

A single Swiss-locale formatter, used on every surface, to eliminate the "`3/12/2025, 8:00:00 AM` in a Swiss legal product" trust-signal failure the design critique called out. Both surfaces pin the formatter to `Europe/Zurich` so SSR, a UTC dev container, and a Swiss operator's laptop all render the same wall-clock time.

| Output    | Example               | Formatter                    |
| --------- | --------------------- | ---------------------------- |
| Date only | `03.04.2026`          | `formatSwissDate(value)`     |
| Timestamp | `03.04.2026, 14:30`   | `formatSwissDateTime(value)` |

- **Locale:** `de-CH` (24-hour clock, leading zeros, dot separators). **Time zone:** `Europe/Zurich`.
- **Source modules:**
  - `legal-search/frontend/src/lib/format/date.ts`
  - `platform-control/admin/src/lib/format/date.ts`
- **Primitives / wrappers:**
  - `<DateText>` (legal-search) — wraps `<time>` with `tabular-nums` so digits align in columns.
  - `<SwissDateField>` (admin) — drop-in replacement for react-admin's `<DateField>` that pins `locales="de-CH"` and the contract's Intl options.
- **Guardrail tests:**
  - `legal-search/frontend/src/__tests__/date-format.cross-surface.test.ts`
  - `platform-control/admin/src/lib/__tests__/date.swiss.test.ts`

Both tests exercise the same fixtures; if both pass, the two surfaces render a given ISO string identically. Never introduce a new `toLocaleDateString` / `Intl.DateTimeFormat` call in product code — route through the formatter.


---

## Future Work

- **Dark Mode:** Brand/surface/interactive tokens have `.dark {}` overrides; keep auditing contrast and focus parity (`TAR-252`)
- **Docling Renderer Migration:** Replace HTML-string rendering in `DetailsTab.tsx` with structured Docling components when the BFF returns canonical document blocks
- **Additional Primitives:** `Chip` component for ContextBar/FilterPanel chip patterns
- **Sprint 2 (TAR-??? — follow-on):** Source Serif 4 on detail headings, tab indicator `transform`-based motion, mobile detail-sheet IA rework, admin/public masthead unification.

## Metadata visibility contract (TAR-258 decision)

**Target:** BFF-owned `visibility` on `MetadataRow` — the BFF is the canonical composition layer (see ADR-0011).

**Current:** The OpenAPI contract defines `MetadataRow.visibility` as optional (`always | default | expanded`). When the BFF sends it, the frontend uses it directly. When omitted, `metadata-visibility.ts` derives visibility from `label` + `documentType` heuristics.

**Why keep both paths:**

- The BFF progressively adopts `visibility` as document-type knowledge grows.
- The frontend heuristic is a safe fallback for fields the BFF hasn't classified yet.
- No contract or codegen changes are needed — the current optional-field design supports progressive adoption.

**Next step:** As the BFF mapper (`document-detail.mapper.ts`) gains per-document-type rules, it should populate `visibility` for all metadata rows. Once coverage is >95%, the frontend heuristic can be deprecated.

## Remaining (tracked in Linear)

Epic **[TAR-243](https://linear.app/tart-baozi/issue/TAR-243)** / project **[Evidara — Design system & UX (ADR-0016)](https://linear.app/tart-baozi/project/evidara-design-system-and-ux-adr-0016-8d1ece16235c)**. Detail tab line variant uses `--tab-indicator-color` and `--tab-active-font-weight` (`TAR-254` done). Cross-surface status vocabulary: [admin status-level table](../../../platform-control/admin/docs/status-level-vocabulary.md) (`TAR-251`). Sprint 1 aesthetic pass: [**TAR-244**](https://linear.app/tart-baozi/issue/TAR-244) (accent-core token family, card elevation, Swiss date contract).

**ADR:** [ADR-0016](../../../docs/adr/adr-0016-design-system-component-contracts.md) (**accepted** — component contracts are team guidance).
