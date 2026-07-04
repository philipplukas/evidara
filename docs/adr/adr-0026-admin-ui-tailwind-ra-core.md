# ADR-0026: Admin UI — Tailwind + ra-core (amending ADR-0015)

## Status

Proposed

**Implementation note:** A spike validating this direction shipped in April 2026 — six Tailwind + `ra-core` ports (list / detail / filter / create / edit / large-detail) coexisted with the MUI originals at `/sources-v2`, `/runs-v2`, `/authorities-v2/*`, `/jurisdictions-v2/*`. Primitives graduated from `_spike/` to `src/ui/primitives/` on 2026-04-18. The **sources** resource has since completed phase P5 (#501): the MUI files were deleted and the Tailwind ports renamed into their canonical `/sources`, `/sources/create`, `/sources/:id/show` locations, wired through `<Resource list/create/show>`. Runs + reference-data resources remain in the coexistence window. This ADR amends the **Decision** section of [ADR-0015](0015-control-plane-admin-frontend-strategy.md) to replace "Next.js + React-admin" with "Next.js + `ra-core` + internal Tailwind primitives", while leaving every other decision in ADR-0015 (backend-only data access, component boundary, API contract) intact.

## Date

2026-04-18

## Context

ADR-0015 chose **Next.js + React-admin (MUI)** for the first operator-admin slice. That choice proved the resource-routing + data-provider patterns well, but after a Pass 3 UX review we found that keeping admin on MUI forever creates three persistent costs:

1. **Duplicate primitive implementations.** Every shared primitive (pills, field cells, buttons, cards, focus rings) exists twice — once in `legal-search/frontend` (Tailwind + shadcn + radix-ui) and once in `platform-control/admin` (MUI + emotion). The two drift at every design change. The Pass 3 findings log (M-8 through UX-11 in [ux-aesthetic-review.md](../runbooks/ux-aesthetic-review.md)) records the running cost of keeping them in sync through prose alone.
2. **Ongoing bundle overhead.** `@mui/material` + `@mui/icons-material` + `@emotion/*` is ~300–400 KB gzipped on the admin bundle with no corresponding user-facing benefit, given how little of MUI's breadth we actually use.
3. **Two visual vocabularies.** Operators navigating between legal-search and admin cross a style boundary that is not meaningful to them. The UX-4 ("pill / badge contract") work aligned the two on prose, but the two stacks still render with subtly different shadows, focus rings, motion curves, and surface chrome.

The Pass 4 spike investigated whether **`ra-core`** (react-admin's headless core: `DataProvider`, `AuthProvider`, `useListController`, `useShowController`, `useEditController`, `useCreateController`, `useGetMany`, `useGetOne`, `useInput`, `useNotify`, `useReference`, `Form`, `Resource`, `CustomRoutes`, validation) could replace the MUI-rendered `react-admin` package while preserving every data-plumbing capability the admin depends on.

It can. The spike ported six pages (sources list/show, runs list/show, authority create/edit, and the graduation included jurisdiction create/edit as trivial pattern copies) with zero MUI imports, and with no architectural surprises. All findings were either design polish (documented in UX-12.1–12.5) or deferred-scope items with known migration paths (Accordion primitive, Select primitive, shell port).

## Decision

- **Replace `react-admin` with `ra-core`** in `platform-control/admin`. Data plumbing, auth, routing, optimistic updates, validation, and `NotificationContextProvider` all come from `ra-core`. Rendering comes from a small internal primitive library (`src/ui/primitives/`) and page components written against those primitives.
- **Drop `@mui/material`, `@mui/icons-material`, and `@emotion/*`** from the admin app's dependencies once every surface has a non-MUI implementation. The shell (`AppShell`, `SidebarMenu`, `Notification` renderer) is the last surface to migrate; until then MUI stays as a transitive dependency of the shell only.
- **Tailwind v4 is the styling stack**, with selective imports (`tailwindcss/theme` + `tailwindcss/utilities` — no preflight) so it coexists with MUI during the coexistence window without clobbering MUI's base styles.
- **Elevation, motion, and accent tokens are CSS custom properties** in `globals.css`, consumed by both MUI's theme (via `var(...)` strings in `designTokens.ts`) and Tailwind utility classes (via `shadow-[var(--shadow-card)]` etc.). This is the single source of truth for all card elevation and accent behaviour across the two stacks during the migration.
- **Primitives live internally first.** `src/ui/primitives/` is the canonical admin UI library today. Once `legal-search/frontend` is ready to consume the same primitives, they promote to a shared workspace package (e.g. `@evidara/ui`) — that promotion is a separate ADR, because it changes monorepo workspace topology.
- **v2 pages coexist with v1 pages** during the migration window. Each new Tailwind page lives at `/<resource>-v2` (or `/<resource>-v2/:id`) via `<CustomRoutes>`; the MUI `<Resource>` entries keep serving their canonical paths. Pages migrate one resource at a time; when a v2 page reaches parity, the v1 MUI file is deleted and the v2 file is renamed (drops the `V2` suffix, moves into the resource's canonical location).

## Consequences

### Positive

- **Single visual vocabulary** between legal-search and admin once graduation completes — no more prose-maintained "these two stacks should look the same".
- **Smaller admin bundle** — dropping MUI + emotion is ~300–400 KB gzipped; Tailwind v4 + radix + lucide adds back a fraction of that.
- **Simpler primitive authoring.** Adding a new primitive (Accordion, Select, Toast) is one Tailwind file that uses `ra-core` hooks, versus forking MUI components and overriding their theme.
- **AI-assisted coding is easier** on hand-written Tailwind primitives than on MUI's theme + `sx` override surface — matches the broader ADR-0015 premise.
- **Form validation, optimistic updates, reference-field deduplication, bulk actions, permissions, undoable mutations** all keep working — they live in `ra-core` hooks, not in the MUI-rendered `react-admin` package.

### Negative

- **react-admin's pre-built MUI views are dropped.** `<Datagrid>`, `<SimpleShowLayout>`, `<SimpleForm>`, `<ReferenceField>`, `<TextField>`, `<TextInput>`, `<SelectInput>` are all re-implemented against `ra-core` hooks. This is mechanical work but not zero work; the spike shows ~1 day per resource once primitives are established.
- **The shell is the biggest single port.** `<Admin>`, `<Layout>`, `<AppBar>`, `<Menu>`, `<Notification>` don't have ra-core equivalents; they need custom `AppShell`, `SidebarMenu`, `AppBar`, and a Toast renderer wired to `NotificationContextProvider`. Worth its own ADR-amendment PR when the time comes.
- **Two visual stacks coexist during the migration window.** Every v2 page inside the still-MUI shell renders a Tailwind content area inside MUI chrome. The "page-in-a-page" feel (logged as UX-12.5) is the visible cost of coexistence — it resolves when the shell migrates.
- **The root `package.json` is not an npm workspace today.** Promoting primitives to a shared package across admin + legal-search requires workspace conversion, which is its own architectural decision and not included here.

### Neutral

- **Existing `react-admin` components stay importable** during the transition. Files not yet ported (`RunDetailSections`, `SourceCreate`, and their MUI-`SelectInput` dependencies) keep using `react-admin` directly; the migration is surface-by-surface, not all-or-nothing.
- **Contract-first remains true.** `platform-control` API contracts don't change. The admin's `dataProvider.ts` and `authProvider.ts` are untouched by the rendering-layer swap.

## Alternatives Considered

### Keep full `react-admin` + MUI

Rejected: every shared primitive stays duplicated between admin and legal-search forever, and the bundle cost stays. The Pass 3 UX review explicitly flagged this as the ceiling on cross-surface coherence.

### Replace `react-admin` entirely with a hand-rolled controller stack

Rejected: the data-plumbing surface of react-admin (optimistic updates, reference-field dedupe, undoable mutations, permissions, validation, notifications) is substantial and getting it wrong costs operator trust. `ra-core` gives us all of that without MUI, so there's no reason to rewrite it.

### Promote primitives to `@evidara/ui` workspace package *before* proving the approach

Rejected for this ADR: workspace conversion changes monorepo topology and wants its own ADR + PR. The spike proved the approach inside `platform-control/admin` first; promotion is a follow-up once a second consumer (legal-search) is ready.

### Use `react-admin`'s `<Admin theme={tailwindCompatibleTheme}>` to push MUI towards our tokens

Rejected: MUI's theming system is expressive but not infinitely expressive — card elevation, motion, focus rings, and surface chrome are only partially themable. The spike tried the "align MUI theme to our tokens" path in Pass 3 (M-8 through UX-11) and that work is what forced the Pass 4 decision in the first place.

## Migration phases

Documented here as the plan of record; each phase is its own PR.

| Phase | Scope | Status |
|-------|-------|--------|
| P1 | Primitives graduated to `src/ui/primitives/`; sources + runs + authority + jurisdiction pages coexist as v2 previews at `/*-v2`. | **Shipped** (this commit, 2026-04-18). |
| P2 | `<Select>` primitive + `SourceCreate` v2 port (unblocks jurisdiction/authority pickers). | Next. |
| P3 | `<Accordion>` primitive + `RunDetailSections` v2 port (replaces the 5-nested-fetch MUI accordion stack). | After P2. |
| P4 | Shell port: `<AppShell>`, `<SidebarMenu>`, `<AppBar>`, `Toast` renderer wired to `NotificationContextProvider`. Drops `@mui/material`, `@mui/icons-material`, `@emotion/*` from the admin `package.json`. | After P3. |
| P5 | v1 MUI files deleted; v2 pages rename (drop `V2` suffix) into canonical resource locations. Admin becomes fully Tailwind-rendered. | **Sources collapsed** (#501): MUI `SourceList`/`SourceShow`/`SourceCreate`/`SourceVersionsSection` deleted, Tailwind ports renamed to canonical + wired via `<Resource list/create/show>`. Runs + reference-data resources still pending. |
| P6 | (Separate ADR) Promote `src/ui/primitives/` to shared workspace package `@evidara/ui`; convert root `package.json` to npm workspaces so `legal-search/frontend` can consume the same primitives. | After P5, conditional on a second consumer appearing. |

## References

- [ADR-0015: Control-Plane Admin Frontend Strategy](0015-control-plane-admin-frontend-strategy.md) — this ADR amends §Decision
- [ADR-0016: Design System Component Contracts](adr-0016-design-system-component-contracts.md) — pill / badge / focus-ring contracts this work inherits
- [Platform-Control React-Admin Migration](../components/platform-control-react-admin-migration.md) — component-level plan; §227 ("Use full React-admin first, not `ra-core`") is superseded by this ADR
- [UX Aesthetic Review runbook](../runbooks/ux-aesthetic-review.md) — Pass 3 findings that motivated this ADR; Pass 4 findings (UX-12.1–12.5) that validated the direction
