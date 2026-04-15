# Design System

> Visual language, tokens, typography, and CSS patterns for Evidara Legal Search.

---

## Token Architecture

All colors are defined as CSS custom properties in [`globals.css`](../src/app/globals.css) and exposed to Tailwind via `@theme inline`. Components never use hardcoded hex — they reference semantic tokens.

### Brand Tokens

| Token | Value | Tailwind Classes |
|-------|-------|-----------------|
| `--brand` | `#2563eb` | `text-brand`, `bg-brand`, `border-brand` |
| `--brand-hover` | `#1d4ed8` | `text-brand-hover`, `hover:text-brand-hover` |
| `--brand-strong` | `#1a2332` | `bg-brand-strong`, `text-brand-strong` |

### Surface Tokens

| Token | Value | Tailwind Class | Usage |
|-------|-------|----------------|-------|
| `--surface-page` | `#fafafa` | `bg-surface-page` | Workspace shell, mobile shell |
| `--surface-panel` | `#ffffff` | `bg-surface-panel` | Panels, cards, sheets, header |
| `--surface-input` | `#f8f9fa` | `bg-surface-input` | Search input background |

### Interactive Tokens

| Token | Value | Tailwind Class | Usage |
|-------|-------|----------------|-------|
| `--interactive-accent-subtle` | brand @ 5% | `bg-interactive-accent-subtle` | Hover backgrounds, active ContextBar tabs |
| `--interactive-accent-muted` | brand @ 10% | `bg-interactive-accent-muted` | Active pin button, nav badge pill |
| `--focus-ring` | brand @ 20% | `focus:ring-focus-ring` | Input focus rings |

### shadcn Semantic Tokens

Inherited from the shadcn theme and used as-is:

| Token | Tailwind Class | Purpose |
|-------|----------------|---------|
| `--muted` | `bg-muted` | Inactive chip/button backgrounds, hover states |
| `--muted-foreground` | `text-muted-foreground` | Secondary text, labels, metadata |
| `--border` | `border-border` | All structural borders |
| `--foreground` | `text-foreground` | Primary text |
| `--background` | `bg-background` | Base page background |

---

## Typography

### Font Stack

| Variable | Family | Weights | Role |
|----------|--------|---------|------|
| `--font-inter` | Inter | 400–700 | All UI text (headings, labels, buttons, metadata) |
| `--font-serif` | Source Serif 4 | 400, 600 | Legal content — snippets, annotations, detail HTML |

Body font set via `--font-inter` on `<body>`. Legal content areas use the `.font-document` utility class defined in `globals.css`:

```css
.font-document {
  font-family: var(--font-serif), "Georgia", serif;
}
```

### Type Scale (5 sizes + 2 display)

| Token | Size | Tailwind | Usage |
|-------|------|----------|-------|
| `text-lg` | 18px | built-in | Wordmark only |
| `text-base` | 16px | built-in | Detail title |
| `text-sm` | 14px | built-in | Result titles, content text, search input |
| `text-xs` | 12px | built-in | Labels, metadata, tabs, filter labels |
| `text-micro` | 11px | `--font-size-micro` | Actions, structural context, breadcrumbs, AccentButton, ActionTextLink |
| `text-tiny` | 10px | `--font-size-tiny` | Badge labels, counts, micro pills |

Both `text-micro` and `text-tiny` are registered as custom Tailwind font-size tokens in `@theme inline`.

### Font Weights

| Class | Weight | Usage |
|-------|--------|-------|
| `font-bold` | 700 | Wordmark "E" |
| `font-semibold` | 600 | Titles, active items, section headers, badges |
| `font-medium` | 500 | Labels, buttons, chip text |
| `font-normal` | 400 | Body text, counts |

---

## Primitives

Reusable design components in [`src/components/primitives/`](../src/components/primitives/). All primitives use design tokens — no hardcoded hex.

**Barrel exports:** see [`primitives/README.md`](../src/components/primitives/README.md) for the authoritative export list (`TAR-267`).

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

Colored document-type pill using the generic palette from [`badge-tokens.ts`](../src/lib/badge-tokens.ts).

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

Defined in [`src/lib/badge-tokens.ts`](../src/lib/badge-tokens.ts). The keys are visual, not semantic:

| Key | Background | Text |
|-----|-----------|------|
| `blue` | `#dbeafe` | `#1e40af` |
| `pink` | `#fce7f3` | `#9d174d` |
| `indigo` | `#e0e7ff` | `#3730a3` |
| `green` | `#d1fae5` | `#065f46` |
| `amber` | `#fef3c7` | `#92400e` |
| `slate` | `#f1f5f9` | `#334155` |
| fallback | `#f3f4f6` | `#374151` |

### Special Context Colors

These use Tailwind's built-in color palette (not tokens) for domain-specific badges:

| Element | Classes | Usage |
|---------|---------|-------|
| Translation badge | `bg-amber-50 text-amber-700` | Machine translation indicator |
| Confidence badge | `bg-green-50 text-green-700` | AI annotation confidence |
| Annotation card | `border-brand/10 bg-brand/[0.02]` | AI/editorial annotation panels |

---

## Spacing & Layout

### Border Radius

| Token | Value |
|-------|-------|
| `--radius` (base) | `0.625rem` (10px) |
| Buttons/inputs | `rounded-lg` / `rounded-md` |
| Chips | `rounded-full` |
| Badges | `rounded` (4px) |

### Common Padding Patterns

| Element | Padding |
|---------|---------|
| Header | `px-6 py-3` |
| Context bar | `px-6 py-2` |
| Filter group body | `px-4 pb-3` |
| Result card | `px-5 py-4` |
| Detail header | `px-5 py-4` |
| Detail tab content | `p-5` |

---

## Elevation & shadows

Structural depth uses **named CSS variables** in [`globals.css`](../src/app/globals.css) (not ad-hoc `shadow-lg` on chrome):

| Token | Typical use |
|-------|----------------|
| `--shadow-shell` | Sticky app header (`box-shadow: var(--shadow-shell)`) |
| `--shadow-control-plane` | Floating control surfaces (e.g. elevated panels tied to brand tint) |

**Rule:** new floating surfaces pick a **named** token or add one with design review; avoid one-off `box-shadow` unless documented here (`TAR-246`, `TAR-261`).

---

## Border hierarchy

| Kind | Classes / token | When |
|------|-----------------|------|
| Structural dividers | `border-border` or `border-border/60`–`/70` | Panel edges, header/footer separators — softer opacity = lower emphasis |
| Input / control outline | `border-border/70` + `focus:border-brand` | Search field, form controls |
| Selection emphasis | `border-l-2 border-l-brand` (transparent when idle) | Result list selection, structure nav current item |
| Dashed empty | `border-dashed border-border/70` | Empty metadata placeholder |

---

## Interactive Patterns

### Transitions

| Pattern | CSS | Duration | Used on |
|---------|-----|----------|---------| 
| Color swap | `transition-colors` | 150ms default | Buttons, links, chips |
| All properties | `transition-all` | 150ms default | Chips, toggles, cards |
| Opacity reveal | `transition-opacity` | 150ms default | Action bar hover |
| Transform slide | `transition-transform` | 150ms default | Toggle switch thumb |

### Selection States

| Element | Selected | Unselected |
|---------|----------|------------|
| Result card | `bg-brand/[0.03] border-l-2 border-l-brand` | `hover:bg-muted/30 border-l-2 border-l-transparent` |
| Detail tab (Radix `line`) | `font-bold text-foreground` + bottom `after:` indicator | `font-medium text-muted-foreground/70` + indicator hidden |
| Structure item | `bg-interactive-accent-subtle text-brand border-l-2 border-l-brand` | `text-foreground/70 hover:bg-muted/50` |
| Chip (ContextBar) | `bg-brand-strong text-white shadow-sm` | `bg-muted text-muted-foreground` |
| Tab (ContextBar) | `text-brand bg-interactive-accent-subtle` | `text-muted-foreground hover:bg-muted` |
| Pin button | `text-brand bg-interactive-accent-muted` (via AccentButton) | `text-muted-foreground` (via AccentButton) |

### Focus States

| Element | Ring | Border |
|---------|------|--------|
| Search input | `ring-2 ring-focus-ring` | `border-brand` |
| Filter search | `ring-1 ring-focus-ring` | — |
| Resize handle | `ring-1 ring-ring` | — |

### Hover Reveal

Action buttons on `ResultCard` use `opacity-0 group-hover:opacity-100 transition-opacity` — invisible until the card is hovered.

---

## Icon System

### Lucide Icons (react)

All icons from `lucide-react`. Standard size: `w-3 h-3` to `w-4 h-4`.

### Emoji Flag Registry

Country/canton flags use emoji via [`icons.ts`](../src/lib/icons.ts):

| Key | Emoji | Display |
|-----|-------|---------|
| `ch` | 🇨🇭 | Switzerland |
| `at` | 🇦🇹 | Austria |
| `ch-zh` | `ZH` | Zürich (text) |
| `ch-be` | `BE` | Bern (text) |
| ... | ... | Other cantons |

Production milestone: replace with SVG flag components or `circle-flags` library.

---

## Future Work

- **Dark Mode:** Brand/surface/interactive tokens need `.dark {}` overrides in globals.css (`TAR-252`, `TAR-264` focus parity)
- **Docling Renderer Migration:** Replace HTML-string rendering in `DetailsTab.tsx` with structured Docling components when the BFF returns canonical document blocks
- **Motion tokens:** Centralize duration/easing for sheets and hovers (`TAR-263`)
- **Token audit:** Replace remaining Tailwind palette exceptions in the table above with semantic tokens (`TAR-260`)

## Remaining (tracked in Linear)

Epic **[TAR-243](https://linear.app/tart-baozi/issue/TAR-243)** / project **[Evidara — Design system & UX (ADR-0016)](https://linear.app/tart-baozi/project/evidara-design-system-and-ux-adr-0016-8d1ece16235c)**. Open items include admin `StatusBadge` migration, `PageContextBar`, dashboard thresholds, Linux VRT, optional BFF metadata `visibility`, and tab active-state token pass (`TAR-254`). Cross-surface status vocabulary: [admin status-level table](../../../platform-control/admin/docs/status-level-vocabulary.md) (`TAR-251`).

**ADR:** [ADR-0016](../../../docs/adr/adr-0016-design-system-component-contracts.md) (**accepted** — component contracts are team guidance).
