# Design System

> Visual language, tokens, typography, and CSS patterns for Omnilex Search.

---

## Color Palette

### Brand Colors

| Token | Value | Usage |
|-------|-------|-------|
| Brand accent | `#2563eb` (blue-600) | Active states, focus rings, links, tab underlines, pivot buttons |
| Brand dark | `#1a2332` | Wordmark logo, active chip backgrounds |
| Brand accent hover | `#1d4ed8` (blue-700) | Hover state for accent links |

### Semantic Colors (CSS Custom Properties)

All theme tokens use `oklch` color space. Light mode only (dark mode tokens present but unused).

| Token | Light | Purpose |
|-------|-------|---------|
| `--background` | `oklch(1 0 0)` | Page background |
| `--foreground` | `oklch(0.145 0 0)` | Primary text |
| `--muted` | `oklch(0.97 0 0)` | Inactive chip/button backgrounds |
| `--muted-foreground` | `oklch(0.556 0 0)` | Secondary text, labels |
| `--border` | `oklch(0.922 0 0)` | All borders |
| `--ring` | `oklch(0.708 0 0)` | Focus ring color |
| `--destructive` | `oklch(0.577 0.245 27.325)` | Error states |

### Badge Colors (type-coded)

| Key | Background | Text | Used for |
|-----|-----------|------|----------|
| `law` | `#dbeafe` | `#1e40af` | Law documents |
| `decision` | `#fce7f3` | `#9d174d` | Court decisions |
| `rechtssatz` | `#e0e7ff` | `#3730a3` | Legal principles |
| `commentary` | `#d1fae5` | `#065f46` | Commentary documents |
| fallback | `#f3f4f6` | `#374151` | Unknown types |

### Special Context Colors

| Element | Color | Usage |
|---------|-------|-------|
| Translation badge | `bg-amber-50 text-amber-700` | Machine translation indicator |
| Confidence badge | `bg-green-50 text-green-700` | AI annotation confidence |
| Annotation card | `border-[#2563eb]/10 bg-[#2563eb]/[0.02]` | AI/editorial annotation panels |

---

## Typography

### Font Stack

| Token | Family | Weights | Role |
|-------|--------|---------|------|
| `--font-inter` | Inter | 400–700 | All UI text (headings, labels, buttons, metadata) |
| `--font-serif` | Source Serif 4 | 400, 600 | Legal content: snippets, annotations, detail HTML |

Body font set via `font-[family-name:var(--font-inter)]` on `<body>`.

### Type Scale

| Usage | Size | Weight | Extra |
|-------|------|--------|-------|
| Wordmark | `text-lg` (18px) | `font-semibold` | `tracking-tight` |
| Card title | `text-sm` (14px) | `font-semibold` | `leading-snug` |
| Detail title | `text-base` (16px) | `font-semibold` | `leading-snug` |
| Section headers | `text-xs` (12px) | `font-semibold` | `uppercase tracking-wider` |
| Body text | `text-sm` (14px) | regular | `leading-relaxed` |
| Metadata labels | `text-[11px]` | `font-medium` | |
| Micro text | `text-[10px]` | `font-semibold` | Badge labels, counts |

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
| Result card | `bg-[#2563eb]/[0.03] border-l-2 border-l-[#2563eb]` | `hover:bg-muted/30 border-l-2 border-l-transparent` |
| Detail tab | `border-b-2 border-[#2563eb] text-[#2563eb]` | `border-transparent text-muted-foreground` |
| Structure item | `bg-[#2563eb]/5 text-[#2563eb] border-l-2 border-l-[#2563eb]` | `text-foreground/70 hover:bg-muted/50` |
| Chip (ContextBar) | `bg-[#1a2332] text-white shadow-sm` | `bg-muted text-muted-foreground` |
| Chip (FilterPanel) | Same as ContextBar | Same |
| Tab (ContextBar) | `text-[#2563eb] bg-[#2563eb]/5` | `text-muted-foreground hover:bg-muted` |
| Pin button | `text-[#2563eb] bg-[#2563eb]/10` | `text-muted-foreground` |

### Focus States

| Element | Ring | Border |
|---------|------|--------|
| Search input | `ring-2 ring-[#2563eb]/20` | `border-[#2563eb]` |
| Filter search | `ring-1 ring-[#2563eb]/30` | — |
| Resize handle | `ring-1 ring-ring` | — |

### Hover Reveal

Action buttons on `ResultCard` use `opacity-0 group-hover:opacity-100 transition-opacity` — invisible until the card is hovered.

---

## Icon System

### Lucide Icons (react)

All icons are from `lucide-react`. Standard size: `w-3 h-3` to `w-4 h-4`.

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
