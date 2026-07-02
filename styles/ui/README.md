# `@evidara/ui` — shared cross-surface primitives

Cross-surface design-system primitives consumed by both `legal-search/frontend`
(workspace) and `platform-control/admin` via a TypeScript path alias.

## Why this exists

Per [ADR-0027](../../docs/adr/0027-workspace-admin-visual-language.md), Evidara
ships **two products, shared brand**. The shared half — palette, focus ring,
status vocabulary, accessibility contracts — needs a single canonical
implementation so both surfaces stay aligned without prose-maintained
"these two should look the same" reminders.

This module is the home for primitives whose contract is shared:

- **Status / pill / badge** primitives (per
  [ADR-0016 Contract 5](../../docs/adr/adr-0016-design-system-component-contracts.md)).
- **Focus-ring affordance** wrappers if and when one becomes the canonical
  shape.
- **Button** if and when the workspace and admin signatures reconcile (today
  they intentionally diverge — see *What does NOT belong here* below).

## Why TS-path-alias and not an npm workspace

[ADR-0028](../../docs/adr/0028-shared-shell-module.md) records the lighter
pattern this module follows. [ADR-0026 §P6](../../docs/adr/adr-0026-admin-ui-tailwind-ra-core.md)
explicitly defers npm workspace conversion to its own ADR + PR — the cost of
restructuring monorepo topology is not yet justified by the size of the
shared surface.

Until that bar is crossed, shared TypeScript modules live under `styles/`
co-located with `styles/tokens/` (the prior precedent), and each surface
exposes them via `tsconfig.json` `paths`:

```jsonc
"@evidara/ui":   ["../../styles/ui"],
"@evidara/ui/*": ["../../styles/ui/*"]
```

Vitest aliases on each surface mirror the tsconfig entry so a test run fails
loudly if the wiring drifts. Turbopack roots in each surface's
`next.config.ts` are already widened to the monorepo root for the existing
`@evidara/tokens` consumer.

## What belongs here

- Primitives that **must render correctly under both token regimes**
  (workspace cream canvas + serif display, admin cool blue + sans density).
- Components whose contract is governed by an ADR-0016 design-system entry
  and is genuinely identical across surfaces (e.g. `StatusBadge` —
  redundant encoding + status tokens).
- Pure presentational + accessibility logic with no surface-specific
  data-fetching or routing dependencies.

## What does NOT belong here

- **Surface-specific cards / shells / data tables.** Workspace narrative
  cards and admin operator/quadrant cards intentionally diverge per
  ADR-0027 — they live in their respective apps.
- **`Button`.** Workspace's `AccentButton` carries consequence-tier
  confirmation logic; admin's `Button` is a minimal semantic-variant
  primitive. Reconciling them is a separate ADR; do not collapse them into
  this module without one.
- **MUI- or react-admin-coupled primitives.** Admin still has a few of
  these during the ADR-0026 P4 shell migration — they belong in
  `platform-control/admin/src/ui/primitives/` until they go.
- **Anything with its own runtime dependencies beyond what both surfaces
  already ship.** React, lucide-react, clsx, and tailwind-merge are present
  on both sides; new dependencies require explicit alignment in both
  surfaces' `package.json`.

## When to revisit (move to npm workspace)

ADR-0028 names the triggers that turn this pattern into an npm workspace
question rather than a path-alias question:

- The shared module gains its own runtime dependencies that the consumers
  do not already have.
- It needs to publish typed sub-paths beyond `index.ts`.
- A third consumer appears (today there are exactly two: workspace and
  admin).

Until then, keep the module flat (single `index.ts` barrel + co-located
sources), keep imports through the alias, and keep the alias-resolution
test green on each surface.

## Files

| File | Role |
|---|---|
| `index.ts` | Barrel; re-exports `StatusBadge`, types, and the status-token map. Also exports `UI_MODULE_VERSION` (sentinel for the alias-resolution gate). |
| `StatusBadge.tsx` | Canonical `StatusBadge` primitive. Workspace API (`status`, `label`, `size?`, `className?`). Tailwind utilities resolve through each surface's `@theme inline` block. |
| `status-tokens.ts` | `StatusLevel` type and `STATUS_TOKEN_MAP` (icon + Tailwind class wiring). |
| `status-badge-token-parity.test.ts` | Parity guard: forbids raw colour literals and Tailwind arbitrary colour values inside this module. |

## Tests

Each surface adds a tiny alias-resolution test (`ui-alias.test.ts`) that
imports from `@evidara/ui` and asserts the sentinel resolves — the cheapest
possible regression net for the path-alias plumbing. The token-parity test
co-located here scans the canonical sources directly.
