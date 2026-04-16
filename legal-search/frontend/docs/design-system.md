# Design System

> Visual language, tokens, typography, and CSS patterns for Evidara Legal Search.

---

## Token Architecture

Shared color tokens live in [`contracts/design-tokens/evidara-tokens.css`](../../../contracts/design-tokens/evidara-tokens.css) and are imported at the top of [`globals.css`](../src/app/globals.css). Tailwind picks them up via `@theme inline`. Components never use hardcoded hex — they reference semantic tokens.

Both `legal-search/frontend` and `platform-control/admin` consume the same shared file, so the brand, surface, interactive, focus, chart, and badge palettes stay identical across apps. App-specific tokens (shadcn semantic tokens, typography sizes) remain local to each app.

### Brand Tokens

| Token | Value | Tailwind Classes |
|-------|-------|-----------------|
| `--brand` | `#0f4c81` | `text-brand`, `bg-brand`, `border-brand` |
| `--brand-hover` | `#0b3d68` | `text-brand-hover`, `hover:text-brand-hover` |
| `--brand-strong` | `#1d293d` | `bg-brand-strong`, `text-brand-strong` |

### Highlight Tokens (secondary accent)

Muted gold. Used sparingly for editorial rails, annotation accents, citation chips, and decorative corners. Do not use for primary actions.

| Token | Value | Tailwind Classes |
|-------|-------|-----------------|
| `--highlight` | `#9a7a4a` | `text-highlight`, `bg-highlight` |
| `--highlight-hover` | `#80623a` | `hover:text-highlight-hover` |
| `--highlight-soft` | `rgb(154 122 74 / 14%)` | used in gradients / washes |
| `--interactive-highlight-subtle` | `rgb(154 122 74 / 10%)` | `bg-interactive-highlight-subtle` |

### Surface Tokens (warm paper)

Page and panel share a warm hue family. Serif legal content and the brand navy both land on a coherent editorial background.

| Token | Value | Tailwind Class | Usage |
|-------|-------|----------------|-------|
| `--surface-page` | `#f4efe7` | `bg-surface-page` | Workspace shell, mobile shell |
| `--surface-panel` | `#fffdf8` | `bg-surface-panel` | Panels, cards, sheets, header |
| `--surface-input` | `#faf6ee` | `bg-surface-input` | Search input background |
| `--surface-shell` | mix(panel 88%, page) | `bg-surface-shell` | Header brand pill, nav bar, utility strip |
| `--surface-shell-strong` | mix(panel 78%, brand 22%) | `bg-surface-shell-strong` | Stronger header accents |

### Interactive Tokens

| Token | Value | Tailwind Class | Usage |
|-------|-------|----------------|-------|
| `--interactive-accent-subtle` | brand @ 8% | `bg-interactive-accent-subtle` | Hover backgrounds, active ContextBar tabs |
| `--interactive-accent-muted` | brand @ 14% | `bg-interactive-accent-muted` | Active pin button, nav badge pill |
| `--interactive-highlight-subtle` | highlight @ 10% | `bg-interactive-highlight-subtle` | Annotation / citation hover |
| `--focus-ring` | brand @ 24% | `focus:ring-focus-ring` | Input focus rings |

### Chart Ramp

Brand-coherent ramp anchored on navy → teal → sage → gold → rose → slate. Lightness-matched so overlaid series stay legible.

| Token | Light | Tailwind Class |
|-------|-------|----------------|
| `--chart-1` | `oklch(0.55 0.12 245)` (navy) | `bg-chart-1`, `text-chart-1` |
| `--chart-2` | `oklch(0.62 0.09 200)` (teal) | `bg-chart-2` |
| `--chart-3` | `oklch(0.68 0.09 155)` (sage) | `bg-chart-3` |
| `--chart-4` | `oklch(0.72 0.10 85)` (gold) | `bg-chart-4` |
| `--chart-5` | `oklch(0.62 0.10 25)` (rose) | `bg-chart-5` |
| `--chart-6` | `oklch(0.48 0.03 250)` (slate) | `bg-chart-6` |

Dark-mode values lift lightness to roughly `0.70–0.80`.

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

**Palette:** blue, pink, indigo, green, amber, slate (+ fallback)
**Sizes:** `sm` (default) and `xs` (preview surfaces)

**Used by:** ResultCard, ExactMatchStrip, RelatedTab

---

## Badge Color Palette

Defined as oklch tokens in [`contracts/design-tokens/evidara-tokens.css`](../../../contracts/design-tokens/evidara-tokens.css) and wired through [`src/lib/badge-tokens.ts`](../src/lib/badge-tokens.ts). The keys are visual, not semantic. All swatches share matched lightness (`bg ≈ L 0.94`, `text ≈ L 0.40`) so every pill carries the same perceived weight regardless of hue.

| Key | Background token | Text token |
|-----|------------------|------------|
| `blue` | `--badge-blue-bg` | `--badge-blue-text` |
| `pink` | `--badge-pink-bg` | `--badge-pink-text` |
| `indigo` | `--badge-indigo-bg` | `--badge-indigo-text` |
| `green` | `--badge-green-bg` | `--badge-green-text` |
| `amber` | `--badge-amber-bg` | `--badge-amber-text` |
| `slate` | `--badge-slate-bg` | `--badge-slate-text` |
| fallback | `--badge-fallback-bg` | `--badge-fallback-text` |

Dark-mode overrides invert the swatches (`bg ≈ L 0.30`, `text ≈ L 0.85`) automatically — no component changes required.

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
| Detail tab | `border-b-2 border-brand text-brand` | `border-transparent text-muted-foreground` |
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
| `ch` | CH | Switzerland |
| `at` | AT | Austria |
| `ch-zh` | `ZH` | Zurich (text) |
| `ch-be` | `BE` | Bern (text) |
| ... | ... | Other cantons |

Production milestone: replace with SVG flag components or `circle-flags` library.

---

## Dark Mode

Brand, highlight, surface, interactive, focus, chart, and badge tokens all ship `.dark` overrides in [`contracts/design-tokens/evidara-tokens.css`](../../../contracts/design-tokens/evidara-tokens.css).

- Brand lifts from navy `#0f4c81` to `#6ea8da` so it reads against dark surfaces without losing identity.
- Surfaces move to warm graphite (`#17181a` / `#1f2023`) rather than neutral gray, preserving the warm-paper feel.
- Badge swatches invert lightness (`bg ≈ 0.30`, `text ≈ 0.85`).
- Interactive/focus/chart tokens all track the lifted brand.

Components that already reference tokens (all primitives, surfaces, headers) pick dark mode up for free. Ad-hoc hex references (e.g. the Special Context Colors above) are the only remaining gap and should migrate as touched.

---

## Future Work

- **Docling Renderer Migration:** Replace HTML-string rendering in `DetailsTab.tsx` with structured Docling components when the BFF returns canonical document blocks
- **Additional Primitives:** `Chip` component for ContextBar/FilterPanel chip patterns
- **Token-ify special-context colors:** Translation / confidence / annotation panels still use Tailwind hex palettes; promote to shared highlight/brand-derived tokens
