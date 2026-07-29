# ADR-0016: Design-System Component Contracts

**Status:** accepted  
**Date:** 2026-04-15  
**Deciders:** Product / engineering  
**Context:** UX review (2026-04-15) identified 8 pattern violations that share a root cause: the codebase treats visual polish as CSS fixes rather than component contracts. This ADR defines the contracts needed so the wrong thing becomes hard to build.

## Decision drivers

- The 6 ad-hoc CSS fixes shipped on 2026-04-15 improve screenshots but don't prevent recurrence.
- Each pattern violation maps to a missing or underspecified component API.
- The admin surface (MUI) and legal-search surface (Tailwind/shadcn) share no status vocabulary.

## Component contract inventory

### What exists today

| Component | Surface | Props | Gap |
|---|---|---|---|
| `ui/badge.tsx` | legal-search | `variant` (default, secondary, destructive, outline) | No `status` prop; no icon slot |
| `primitives/Badge.tsx` | legal-search | `colorKey`, `size` | Hex from `badge-tokens.ts`; no semantic status |
| `ui/tabs.tsx` | legal-search | `variant` (default, line) | Radix triggers expose `aria-selected`; polish two-dimensional active styling via tokens (`TAR-254`) |
| `DetailTabs.tsx` | legal-search | `tabs` + nuqs `tab` | Composes Radix `Tabs`; URL sync covered by tests — strengthen token-driven active contrast (`TAR-254`) |
| `MetadataList.tsx` | legal-search | `fields`, `initialDensity?`, `showHeading?` | Density + progressive disclosure shipped; `DetailMetadataRow.visibility` is **required** and BFF-owned — the client-side label heuristics were removed in #787 |
| `FilterPanel.tsx` | legal-search | `filters` | Delegates refinement chips to `FilterBar`; panel layout / filter groups still evolve with `TAR-255` |
| `ContextBar.tsx` | legal-search | `context` | Jurisdiction / language / source chips; refinements live in `FilterPanel` / `FiltersSheet` + `FilterBar` — document vs `ResultsControlRegion` (`TAR-256`) |
| MUI `Chip` | admin | `color`, `variant`, `size` | Status color maps are local to each file (`STATUS_COLORS`, `HEALTH_COLORS`, `TONE_ACCENTS`) |
| `SourceVersionsSection.tsx` | admin | None | Version badges use color-only differentiation |

### What's needed: 8 component contracts

Each contract below specifies: what the component owns, what props it exposes, and the invariant it enforces.

---

## Contract 1: `FilterBar`

**Pattern:** Filter Bar with Active State Summary (NN/g, Material Filters)

**Owns:** Chip rendering, active-count badge, per-chip dismiss, clear-all affordance.

**Props:**

```ts
interface FilterBarProps {
  filters: FilterViewModel[];
  onDismiss: (filterKey: string, value: string) => void;
  onClearAll: () => void;
  activeCount: number;
}
```

**Invariant:** Clear-all is visible if and only if `activeCount > 0`. Both desktop and mobile consume the same component — desktop renders inline, mobile renders inside a sheet.

**Replaces:** Ad-hoc reset button in `ContextBar.tsx`, separate `FilterPanel.tsx` clear/reset logic.

**Migration:** Extract from existing `FilterPanel` + `ContextBar`. The `ContextBar` becomes a layout container that composes `FilterBar` + constraint chips.

---

## Contract 2: `ResultsControlRegion`

**Pattern:** Control Grouping by Function (Gestalt proximity)

**Owns:** The single bounded region where all result-narrowing, sorting, and toggling controls live. Nothing outside this region may mutate the result list.

**Props:**

```ts
interface ResultsControlRegionProps {
  children: ReactNode; // FilterBar, sort controls, official-only toggle
}
```

**Invariant:** Every control that calls `dispatch` on `SearchConstraintsProvider` must be a child of `ResultsControlRegion`. This is an IA rule enforced by convention and documented in the design-system spec.

**Replaces:** The current split between `ContextBar` (chips + toggle) and `FilterPanel` (left panel). The toggle moves inside the region permanently.

---

## Contract 3: `Tabs` (enhanced)

**Pattern:** WAI-ARIA Tabs with Selected State (WCAG 1.4.1)

**Extends:** Existing `ui/tabs.tsx` (Radix).

**Required changes:**

- Active state uses TWO dimensions: color + weight, or color + indicator bar.
- `aria-selected="true"` is wired on the active tab (not `aria-current`).
- Selected state is token-driven: `--tab-indicator-color`, `--tab-active-weight`.

**Props (additions to existing):**

```ts
// The Radix TabsTrigger already manages aria-selected.
// DetailTabs.tsx should migrate to use Radix Tabs instead of custom buttons.
```

**Invariant:** It is impossible to render a tab set where the active tab differs from inactive by only one visual dimension.

**Migration:** `DetailTabs.tsx` should wrap Radix `Tabs` primitives from `ui/tabs.tsx` and apply the `line` variant, which already has an indicator. Remove the custom button-based implementation.

---

## Contract 4: `MetadataList`

**Pattern:** Progressive Disclosure + Information Density Levels (Shneiderman)

**Owns:** Rendering a list of key-value metadata pairs at a specified density level.

**Props:**

```ts
type MetadataDensity = "compact" | "default" | "expanded";

interface MetadataField {
  key: string;
  label: string;
  value: string | ReactNode;
  iconKey?: string;
  visibility: "always" | "default" | "expanded";
}

interface MetadataListProps {
  fields: MetadataField[];
  density: MetadataDensity;
}
```

**Invariant:** Fields with `visibility: "always"` render at every density level. Fields with `visibility: "expanded"` only render at `expanded`. The component cannot render zero fields — if all fields are filtered out, it shows a "No metadata available" empty state.

**Replaces:** The prior unconditional metadata block (`MetadataSection.tsx`, removed); detail now composes `MetadataList` from `DetailsTab.tsx`.

**Schema implication:** The BFF API's `metadata` array needs a `visibility` field (or the frontend defines a static config per document type).

---

## Contract 5: `StatusBadge`

**Pattern:** Redundant Encoding (WCAG 1.4.1) + Semantic Status Tokens

**Owns:** Rendering a status indicator with color + icon + label together. There is no way to use the component with color only.

**Props:**

```ts
type StatusLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

interface StatusBadgeProps {
  status: StatusLevel;
  label: string;
  size?: "sm" | "md";
}
```

**Token mapping (defined in design system, not per-instance):**

| Status | Color token | Icon | Example |
|---|---|---|---|
| `healthy` | `--status-healthy` (green) | `CheckCircle` | "Active", "Approved", "ok" |
| `degraded` | `--status-degraded` (amber) | `AlertTriangle` | "Pending", "blocked", "in_progress" |
| `critical` | `--status-critical` (red) | `XCircle` | "Failed", "Rejected", "critical" |
| `neutral` | `--status-neutral` (gray) | `MinusCircle` | "Archived", "Superseded", "unavailable" |
| `info` | `--status-info` (blue) | `Info` | "Running", "Draft" |

**Invariant:** The `status` prop drives color, icon, and label together. Consumers cannot override color independently.

**Replaces:**

- Admin: `STATUS_COLORS`, `HEALTH_COLORS`, `TONE_ACCENTS` local maps in `Dashboard.tsx`, `RunList.tsx`, `RunShow.tsx`, `SourceList.tsx`
- Admin: `SOURCE_STATUS_META` in `SourceShow.tsx`
- Legal-search: Version badge chips in any future admin-adjacent views

**Shared across surfaces:** This component must work in both MUI (admin) and Tailwind (legal-search) contexts. Implement as a headless contract with two renderers, or as a shared token set.

**Status (2026-04-29):** Stream A migration shipped — the canonical
`StatusBadge` source now lives in `@evidara/ui` (`styles/ui/StatusBadge.tsx`)
and is consumed by both `legal-search/frontend` (`@/components/primitives`
re-export shim) and `platform-control/admin` (`Pill` adapter that delegates
the status-variant rendering to `StatusBadge` and keeps the admin-only
`meta` chip variant local). The shared module is exposed via the
`@evidara/ui` TypeScript path alias rather than an npm workspace package —
see [ADR-0028](0028-shared-shell-module.md) for the pattern, which mirrors
the existing `@evidara/tokens` precedent and defers npm workspace
conversion per [ADR-0026 P6](adr-0026-admin-ui-tailwind-ra-core.md).

---

## Contract 6: `PageContextBar`

**Pattern:** Persistent Context Header (sticky summary)

**Owns:** A sticky header that shows the canonical identity of what the user is looking at, persisting on scroll.

**Props:**

```ts
interface PageContextBarProps {
  title: string;
  subtitle?: string;
  status?: StatusLevel;
  statusLabel?: string;
  actions?: ReactNode;
}
```

**Invariant:** The bar sticks to the top of the viewport on scroll. It always shows the title and status. Used on every detail-heavy admin page (run detail, source detail).

**Replaces:** The current run detail page where scrolling deep into artifacts loses sight of run status.

---

## Contract 7: `Stat` (with threshold)

**Pattern:** Status-at-a-Glance / Semantic Status Tokens

**Extends:** The existing `StatCard` in `Dashboard.tsx`.

**Props:**

```ts
interface StatProps {
  label: string;
  value: number | string;
  threshold?: { warn: number; critical: number };
  format?: "number" | "percent" | "duration";
}
```

**Invariant:** When `threshold` is provided, the component automatically applies the correct `StatusLevel` based on the value. A 80% success rate with `threshold: { warn: 95, critical: 80 }` renders as `degraded`, not `default`.

**Replaces:** The current `StatCard` which uses a manually-passed `tone` prop.

---

## Contract 8: `Button` (with consequence tier)

**Pattern:** Action Hierarchy + Destructive/Consequential Confirmation

**Extends:** Existing `ui/button.tsx`.

**Props (addition):**

```ts
type ConsequenceTier = "safe" | "notable" | "destructive";

interface ButtonProps {
  // ... existing variant, size
  tier?: ConsequenceTier;
  confirmLabel?: string; // required when tier is "notable" or "destructive"
}
```

**Behavior by tier:**

- `safe`: No confirmation. Default.
- `notable`: Inline popover confirmation before action fires.
- `destructive`: Modal confirmation with explicit action label.

**Invariant:** A button with `tier="destructive"` cannot fire its `onClick` without user confirmation. The confirmation pattern is enforced by the component, not the consumer.

**Replaces:** The current pattern where "Preview Run" and "Production Run" sit adjacently with no hierarchy or confirmation difference.

---

## Migration order (recommended)

The contracts have dependencies. Recommended sequence:

| Phase | Component | Why first |
|---|---|---|
| 1 | `StatusBadge` + status tokens | Unblocks both surfaces; highest reuse (admin + legal-search) |
| 1 | `Tabs` enhancement | Small change; fixes WCAG violation; already has Radix foundation |
| 2 | `FilterBar` | Formalizes the ad-hoc work already done in ContextBar |
| 2 | `MetadataList` | Needed for detail panel density fix |
| 3 | `PageContextBar` | Admin-only; depends on `StatusBadge` |
| 3 | `Stat` threshold | Admin-only; depends on status tokens |
| 4 | `ResultsControlRegion` | IA rule; enforced by convention after FilterBar exists |
| 4 | `Button` consequence tier | Broadest change; every existing button is `tier="safe"` by default |

## Consequences

**What changes:**

- New components get an API contract before visual implementation.
- Status representation is centralized in tokens, not per-file color maps.
- The 8 pattern violations become structurally impossible to reintroduce.

**What doesn't change:**

- Existing ad-hoc fixes remain in place until migration replaces them.
- The BFF API contract is unchanged (component-side mapping).

**Risks:**

- Two-renderer approach for `StatusBadge` (MUI + Tailwind) adds complexity.
- `MetadataList` density depends on a content-modelling decision (which fields are "always" vs "on demand"). **Decision (TAR-258):** BFF-owned `visibility` is the target state; the frontend fallback in `metadata-visibility.ts` remains as a graceful degradation path until the BFF populates `visibility` for all document types.

  **Amended (#787, 2026-07-21):** the fallback is deleted and `visibility` is now **required**, on its own schema `DetailMetadataRow`. The graceful-degradation path was never graceful: it matched rows against English label regexes (`/^(court|jurisdiction|date|enacted)$/i`) while the BFF emits localized labels ("Zuständigkeit", "In Kraft"), so it could not fire and every unmatched row resolved to `expanded` — which `filterByDensity` hides at both compact and default density. A row would simply not render, with no error. A localized display label is not a join key; keying on it would have needed a fresh pattern set per locale. The BFF already set `visibility` on all 8 of its `rows.push` branches, so requiring it matches the behaviour that was already shipping. Search-result rows keep the visibility-free `MetadataRow` — result cards have no density control.
- `Button` consequence tier is the largest blast radius change — every action in the system needs tier classification.
