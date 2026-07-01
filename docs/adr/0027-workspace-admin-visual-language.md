# ADR-0027: Workspace ↔ Admin Visual Language — Two Products, Shared Brand

## Status

Accepted

## Date

2026-04-23

## Context

Evidara ships two surfaces side-by-side, each optimized for a different user mode:

- **Workspace** (`legal-search/frontend`) — the user-facing reading experience for
  lawyers. Warm cream canvas (`--surface-page`), serif headings (Source Serif 4),
  editorial spacing, navy + violet with a single-accent interactive rule. Optimized
  for long-form, low-velocity, deep-focus reading.
- **Admin** (`platform-control/admin`, primarily the `-v2` Tailwind + `ra-core`
  routes) — the operator UI for source lifecycle, runs, approvals, and reference
  data. Cool blue top bar, compact left nav, dense tables, quadrant decision-support
  cards. Optimized for operator scan, high-velocity control, and dense status grids.

The palette (navy + violet) and a core set of tokens in `styles/tokens/tokens.css`
are already shared — the admin app imports the same `tokens.css` as
`legal-search/frontend` (see `platform-control/admin/src/app/globals.css:22`).
Density, card treatment, typography, and accent usage, however, diverge sharply.
An external review of #384 flagged the result as *"consistent enough to feel
same-company, different enough to read as two products — deliberate split is
fine, but document it, otherwise it looks like drift."*

Issue [#392](https://github.com/philipplukas/evidara/issues/392) asks which of
two stances we are committing to, so that future work on admin (e.g. #386, #387)
and workspace proceeds with a shared premise rather than relitigating the
direction per PR. This ADR records that decision and names the shared tokens
and intentional divergences so contributors do not accidentally drift further.
It builds on [ADR-0015](0015-control-plane-admin-frontend-strategy.md)
(admin lives under `platform-control/admin`, not inside `legal-search`) and
[ADR-0026 (MUI → Tailwind + `ra-core`)](adr-0026-admin-ui-tailwind-ra-core.md)
(the admin is migrating to Tailwind primitives that *could* converge further
on workspace styling if we chose to — this ADR decides that we do not).

## Alternatives Considered

### Stance 1 — Same product, two modes

Summary, paraphrased from #392: *"user and operator are two sides of the same
coin; visuals should share more than the palette. Implies: pull admin-v2 toward
the warmer workspace aesthetic (serif section heads, cream subsurface on detail
cards), keep density but soften surfaces."*

- **Pro:** simplest brand story — one product, one look. A shared component
  library can assume a single rendering context end-to-end.
- **Pro:** contributors think about one typography + elevation stack, not two.
- **Con:** blurs the primitive / customization boundary. Operator-density work
  (dense tables, quadrant cards, compact status grids) has to compromise with
  the workspace reading aesthetic, or vice versa.
- **Con:** forces a design sprint *today* to bring admin-v2 toward the workspace
  aesthetic, blocking #386 / #387 and future admin work on a design decision
  that is not load-bearing for either surface's actual user mode.
- **Con:** makes future admin-specific patterns (operator density, scan-oriented
  typography, denser spacing scales) harder to justify — each one becomes a
  perceived drift from the "one look" promise.

### Stance 2 — Two products, shared brand *(selected)*

Summary, paraphrased from #392: *"Evidara (reader) and Evidara Ops (operator)
are different audiences, different tasks, and shouldn't share a look beyond
brand marks. Implies: formalize the split in an ADR, document the shared
primitives (palette, spacing scale, focus ring) and the intentional divergences
(typography, density, card patterns)."*

- **Pro:** clean primitive / customization boundary. Shared primitives carry
  brand, accessibility, and interaction contracts; each surface layers the
  typography and density appropriate to its user mode on top.
- **Pro:** each surface can optimize for its user mode without
  cross-contamination — workspace keeps its editorial spacing and serif display;
  admin keeps its operator density and scan-oriented chrome.
- **Pro:** unblocks #386, #387, and future admin polish without waiting on a
  cross-surface design sprint.
- **Pro:** aligns with the direction ADR-0026 is already going — a small shared
  token set plus surface-specific primitives that consume those tokens.
- **Con:** a shared component library cannot assume identical tokens beyond
  the shared set; contributors adding primitives must think about two rendering
  contexts.
- **Con:** requires discipline — without a recorded stance (this ADR) the
  divergences read as drift rather than intent. Mitigation: this ADR, plus the
  "shared vs surface-specific" annotation described in *Consequences* below.

## Decision

We adopt **Stance 2 — two products, shared brand.**

The two surfaces share, and will continue to share:

- **Palette** — the navy + violet core, including `--brand`, `--brand-strong`,
  `--accent-core`, and the derived states.
- **Spacing scale** — the base rem-based scale in `styles/tokens/tokens.css`.
  Surfaces apply the scale at different densities; the scale itself is shared.
- **Focus-ring affordance** — identical ring width, offset, colour token, and
  keyboard-visible behaviour across both surfaces.
- **Core tokens in `styles/tokens/tokens.css`** — the canonical source already
  imported by both `legal-search/frontend` and `platform-control/admin`.
- **Base font-stack families** — the same humanist and serif families are
  declared; each surface chooses which to foreground.
- **Accessibility contracts** — WCAG AA contrast minimums, 44×44 touch targets,
  keyboard-navigation patterns, accessible-name conventions, and the pill /
  badge / focus-ring rules from
  [ADR-0016 (design-system component contracts)](adr-0016-design-system-component-contracts.md).
- **Brand voice and brand marks.**

The two surfaces intentionally diverge on:

- **Typography** — workspace foregrounds Source Serif 4 with editorial
  line-heights across page titles, section heads, and body reading; admin
  uses Source Serif 4 only at the display level (top-bar wordmark, page
  `<h1>` titles) and stays sans for section heads, body, and table content
  tuned for operator density. Both surfaces share the same serif face — the
  divergence is now *which levels of the type scale render in serif*, not
  whether serif is used at all. See the 2026-04-28 amendment below.
- **Card and section patterns** — workspace uses soft elevation and narrative
  framing (editorial section heads, cream subsurfaces); admin uses a denser
  grid with structured labels and quadrant decision-support cards.
- **Density** — workspace uses reading spacing (wider paddings, taller line
  boxes); admin uses scan spacing (compact rows, dense status grids).
- **Accent usage** — both surfaces now apply the workspace single-accent
  rule to *primary action* affordances (Promote / Approve render in
  `--accent-core`, destructive actions in `--status-critical`). Admin
  continues to use accent and status colours in non-action contexts —
  status pills, decision-support cards, attention CTAs — where
  scan-velocity justifies a denser colour vocabulary than workspace
  permits in its reading surface. See the 2026-04-28 amendment below.

This is the recorded direction for future design work. #386, #387, and any
further admin visual polish proceed under this stance without waiting on
further cross-surface design direction.

## Consequences

### Positive

- **#386 / #387 unblocked** and future admin work proceeds with a shared premise.
- **Workspace and admin each optimize for their user mode** — long-form reading
  vs operator scan — without compromising either.
- **The shared-token surface is small and explicit**, which makes
  accessibility and brand-consistency regressions easier to catch (they show
  up as a shared-token change, not a whole-app restyle).

### Negative

- **Contributors must think about two rendering contexts** when adding shared
  primitives. Primitives are expected to render correctly under both the
  workspace and admin token regimes.
- **Occasional cross-surface drift is still possible** (e.g. focus-ring colour
  regressing in one surface). Mitigations today: the shared surface lives in
  a single file (`styles/tokens/tokens.css`) so drift is visible in one diff,
  and `legal-search/frontend` has axe assertions (e.g.
  `workspace-client.a11y.test.tsx`) that catch shared-surface regressions for
  the workspace side. As of 2026-04-28, `platform-control/admin` has equivalent
  axe coverage in `src/__tests__/admin-*.a11y.test.tsx` (shell-level + run
  queue resource page), so cross-surface a11y regressions are now caught
  symmetrically.

### Neutral

- **No breaking token changes.** The shared token set is already what both
  surfaces import. This ADR records the *stance*, not a migration.
- **`styles/tokens/tokens.css` should grow a short comment** naming which
  tokens are *shared* (palette, spacing scale, focus ring, core states) vs
  *workspace-specific* (any serif-display-specific or cream-subsurface tokens
  that only workspace consumes). Contributors extending either surface can
  then tell at a glance whether their new token belongs in the shared file or
  in a surface-local `globals.css`. Implementing that annotation is a
  follow-up, not a prerequisite for this ADR.

### Implementation follow-ups

- **Token-ownership annotation** in `styles/tokens/tokens.css` as described
  above (small, docs-only).
- **Admin-specific extensions** remain in `platform-control/admin/src/app/globals.css`
  and must not leak into `styles/tokens/tokens.css`. Workspace-specific
  extensions likewise stay inside `legal-search/frontend`'s `globals.css`.
- **Shared primitives** (button, input, focus ring, pill/badge per ADR-0016)
  must render correctly under both token regimes. Surface-specific
  components — workspace narrative cards, admin operator cards / quadrant
  decision-support cards — live in their respective apps and are not
  candidates for promotion to a shared package.
- **Non-negotiables across both surfaces:** identical WCAG AA contrast,
  identical focus-ring affordance, identical accessible-name conventions,
  and the same keyboard-navigation patterns. Any cross-surface regression on
  these is a bug, not an intentional divergence.

### Implications for related work

- **[#393 — quadrant hierarchy](https://github.com/philipplukas/evidara/issues/393)**
  proceeds as an admin-surface pattern without needing to reconcile with
  workspace card conventions.
- **[#391 — mobile profile card](https://github.com/philipplukas/evidara/issues/391)**
  proceeds as a workspace-surface pattern with workspace typography and
  spacing.
- **[#386](https://github.com/philipplukas/evidara/issues/386) /
  [#387](https://github.com/philipplukas/evidara/issues/387)** and further
  admin visual work do not require a cross-surface design sprint before
  proceeding.

## Amendment — 2026-04-28 — convergence on shared typography, action palette, and foreground hierarchy

Stance 2 still holds. This amendment records that, between 2026-04-27 and
2026-04-28, five PRs implemented the "shared brand" half of the stance more
deeply than the original ADR anticipated, narrowing (but not removing) the
listed divergences for typography and accent usage. The "two products" half
— density, card patterns, and structural chrome — is unchanged.

### What is now shared (was divergent or under-specified at acceptance)

- **Display typography.** Source Serif 4 is now the display face on both
  surfaces. The admin top-bar wordmark adopted it as part of the foundational
  parity sweep ([#477](https://github.com/philipplukas/evidara/pull/477)),
  and admin page-level `<h1>` titles followed in
  [#486](https://github.com/philipplukas/evidara/pull/486). Section heads
  (`<h2>` / `<h3>`) inside admin decision-support, pipeline-health, and
  resource-detail cards intentionally stay sans, so admin still reads as
  operator-dense at the body and section level.
- **Primary-action palette.** The workspace single-accent rule (one accent
  per affordance — `--accent-core` for primary, `--status-critical` for
  destructive) now applies to admin action affordances too, via the MUI
  theme bridge in `platform-control/admin/src/lib/admin/muiTheme.ts` and
  the targeted resource-literal sweep in
  [#487](https://github.com/philipplukas/evidara/pull/487). Admin retains
  accent and status colours outside the action surface (status pills,
  quadrant decision-support cards, "Open attention run" amber CTAs).
- **Foreground / border hierarchy.** The token ladder
  (`--foreground-muted` / `--foreground-subtle` / `--foreground-faint` /
  `--foreground-ghost`, plus `--border-faint` / `--border` / `--border-strong`)
  was added in [#486](https://github.com/philipplukas/evidara/pull/486) and
  [#488](https://github.com/philipplukas/evidara/pull/488) routed all
  previously-handwritten `rgba(29,41,61, X)` and `rgba(15,76,129, X)`
  literals across admin resources through it (69 replacements across 7
  files). Admin foreground hierarchy is now expressed in the same token
  vocabulary the workspace uses.

### What remains intentionally divergent

The original Stance 2 logic still applies to:

- **Density.** Admin keeps scan spacing (compact rows, dense status grids)
  and workspace keeps reading spacing.
- **Card and section patterns.** Admin keeps quadrant decision-support
  cards and structured operator labels; workspace keeps narrative cards
  with editorial section heads and cream subsurfaces.
- **Structural chrome (header, nav).** Admin keeps its cool-blue compact
  top bar and left nav; workspace keeps its reading-surface header.
  Cross-surface header unification (`packages/brand-shell` extraction) is
  follow-up work tracked separately and is *not* part of this amendment.

### CI guard against re-drift

The convergence above is now enforced by the brand-token parity test at
[`platform-control/admin/src/ui/primitives/admin-primitive-token-parity.test.ts`](../../platform-control/admin/src/ui/primitives/admin-primitive-token-parity.test.ts).
The test originally scanned a hand-listed set of admin primitives;
[#491](https://github.com/philipplukas/evidara/pull/491) extended it to walk
`platform-control/admin/src/resources/**/*.tsx` recursively, asserting that
the shared `FORBIDDEN_LITERALS` list (the pre-parity Material hex codes
and the navy / brand-strong rgba opacity literals) cannot be reintroduced
anywhere in the resource tree. Drift on the convergence above now fails
`npm run check`, not code review.

### PRs that landed this convergence

- [#477](https://github.com/philipplukas/evidara/pull/477) — foundational
  shared-token parity for admin shell, primitives, and AppBar typography;
  introduced the primitive-scope brand-token parity test.
- [#486](https://github.com/philipplukas/evidara/pull/486) — admin page-title
  serif and the `--foreground-*` / `--border-*` token ladder.
- [#487](https://github.com/philipplukas/evidara/pull/487) — admin action
  palette aligned with workspace via MUI theme bridge and resource literal
  sweep.
- [#488](https://github.com/philipplukas/evidara/pull/488) — admin
  foreground / border literal sweep onto the token ladder.
- [#491](https://github.com/philipplukas/evidara/pull/491) — parity test
  extended to scan admin resource components.

## References

- Issue: [#392 — workspace ↔ admin-v2 visual language — same product or sibling products?](https://github.com/philipplukas/evidara/issues/392)
- [ADR-0015: Control-Plane Admin Frontend Strategy](0015-control-plane-admin-frontend-strategy.md)
- [ADR-0016: Design System Component Contracts](adr-0016-design-system-component-contracts.md)
- [ADR-0026: Admin UI — Tailwind + `ra-core` (amending ADR-0015)](adr-0026-admin-ui-tailwind-ra-core.md)
- [AGENTS.md](../../AGENTS.md) — source-of-truth hierarchy (design tokens live at `styles/tokens/tokens.css`, consumed by both surfaces)
- [UX aesthetic review runbook](../runbooks/ux-aesthetic-review.md) — Pass 3/4 findings that motivated the direction
