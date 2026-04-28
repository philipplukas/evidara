# ADR-0028: Shared Shell Module — `@evidara/shell` Path Alias

## Status

Proposed

## Date

2026-04-28

## Context

[ADR-0027](0027-workspace-admin-visual-language.md) committed Evidara to "two
products, shared brand". The brand-parity track (PRs #477, #486, #487, #488,
#491) widened the *shared* half — Source Serif 4 display type, the
`--accent-core` interactive rule, and the foreground / border ladder now apply
on both `legal-search/frontend` and `platform-control/admin`. The amendment in
PR #492 records that convergence and explicitly names the cross-surface header
unification as a *separately tracked follow-up*.

Header chrome that is genuinely identical across both surfaces today (the
gradient brand mark "E" tile + Evidara wordmark) is duplicated as two
hand-maintained copies — one in `legal-search/frontend/src/components/layout/AppHeader.tsx`
and one in `platform-control/admin/src/ui/shell/AppBar.tsx`. PR #496 is
unifying *the brand mark itself* in flight; the rest of the header chrome
(profile chip, locale switcher, theme toggle, help button) is currently only
on the workspace side and may or may not migrate to admin later.

[ADR-0026](adr-0026-admin-ui-tailwind-ra-core.md) explicitly defers npm
workspace conversion ("workspace conversion changes monorepo topology and
wants its own ADR + PR"). For now, shared TypeScript modules are exposed via
`tsconfig.json` `paths` aliases — that is the established pattern for
`@evidara/tokens` (`styles/tokens/tokens.ts`).

## Decision

Introduce a sibling shared module **`@evidara/shell`** at `styles/shell/`,
co-located with `styles/tokens/`, exposed to both Next.js apps via
`tsconfig.json` `paths`:

```jsonc
"@evidara/shell":   ["../../styles/shell"],
"@evidara/shell/*": ["../../styles/shell/*"]
```

Vitest aliases on each surface mirror the tsconfig entry so that test runs
fail fast if the wiring drifts. Turbopack roots in `next.config.ts` are
already widened to the monorepo root on both surfaces (a prerequisite for
the existing `@evidara/tokens` alias).

This first slice is **scaffolding only** — `styles/shell/index.ts` exports
a single `SHELL_MODULE_VERSION` sentinel, and a tiny alias-resolution test
on each surface imports it. No header component is migrated in this PR.
The brand mark migration is owned by PR #496; subsequent shareable chrome
(if any — the two headers diverge sharply today) lands in follow-up PRs that
move one component at a time.

## Consequences

### Positive

- **Mechanical wiring lands once, in isolation.** The first real shared
  component PR (whether that's the brand mark via #496 evolving to consume
  `@evidara/shell`, or a later candidate) does not need to also debate
  monorepo topology.
- **Pattern symmetry with `@evidara/tokens`.** Contributors already know the
  shape — same alias style, same co-location under `styles/`, same vitest
  mirror, same Turbopack root.
- **Fail-loud guard.** The `shell-alias.test.ts` on each surface is the
  cheapest possible regression net for the path-alias plumbing.

### Negative / risks

- **Two ways to ship cross-surface code (alias vs. proper package).**
  When `@evidara/shell` grows to the point that semver, dependency hoisting,
  or a separate build step starts to hurt, npm workspace conversion becomes
  the right move (per ADR-0026 P6). This ADR is explicitly the
  *pre-workspace* compromise and should be revisited when:
  - the shared module gains its own runtime dependencies, or
  - it needs to publish typed sub-paths beyond `index.ts`, or
  - a third consumer appears.
- **No physical isolation.** Either app can still import deep into the
  other's source if a contributor ignores the alias and reaches across with
  a relative path. Reviewer discipline only.
- **Sentinel-only exports today.** Until a real component lands, the module
  has no functional value beyond proving the wiring resolves.

## Alternatives considered

1. **Convert root `package.json` to npm workspaces; publish `@evidara/ui`
   and `@evidara/shell` as proper packages.** Rejected for this PR — same
   reasoning as ADR-0026 P6: workspace conversion is its own architectural
   decision and PR. Premature here when the shared surface is tiny.
2. **Keep copy-paste between `AppHeader.tsx` and `AppBar.tsx`.** Rejected
   because the brand-parity track has already proven that drift is the
   default outcome; PR #491 added a parity test specifically because manual
   discipline did not hold. A shared module is the lower-cost guardrail.
3. **Migrate one component (brand mark, locale switcher, profile chip)
   today as part of this PR.** Rejected because (a) the brand mark is owned
   by PR #496 and (b) the rest of the workspace header chrome (locale
   switcher, theme toggle, profile chip, help button) is currently only on
   the workspace side — there is no genuinely duplicated non-brand-mark
   component to migrate first. Ship scaffolding only; let the next real
   shareable component land in a follow-up that can focus entirely on the
   migration.

## References

- ADR-0027 (Two products, shared brand) and its 2026-04-28 amendment (#492).
- ADR-0026 (Admin UI Tailwind + `ra-core`) — P6 defers workspace conversion.
- ADR-0016 (Design system component contracts) — the broader design-system
  governance this slot under.
- PR #496 — brand-mark unification (in flight, owns the brand-mark migration).
- PR #492 — call-out naming the brand-shell follow-up.
