# `@evidara/brand-shell`

Shared brand chrome — the gradient `E` mark, the `Evidara` wordmark lockup, and a thin `<BrandHeader>` slot wrapper — consumed by both `legal-search/frontend` and `platform-control/admin`.

This package exists because the two surfaces had been re-implementing the brand mark and wordmark in two visually divergent forms. After the late-April 2026 brand-parity track (#486–#491) routed both surfaces through the same token ladder, the brand chrome itself was the last visible "two products" tell. This package consolidates that single piece into one source of truth.

## Scope (and what stays out)

- **In scope:** `<BrandMark>` (the gradient "E"), `<BrandLockup>` (mark + wordmark + optional sub-label), `<BrandHeader>` (a slot-based wrapper around `<header>` for the brand/primary/utility regions).
- **Not in scope:** buttons, inputs, focus rings, pills, badges, narrative cards, operator cards. Those primitives stay in their respective apps under ADR-0016 and ADR-0027 ("two products, shared brand"). This package is specifically about the lockup that crosses both surfaces.

## How both apps consume it

There is no npm install step. The package is a path-aliased TS source under `packages/brand-shell`. Both apps already pull shared TS source from the monorepo root via the same pattern (`@evidara/tokens` → `styles/tokens/tokens.ts`).

In each consuming app's `tsconfig.json`:

```json
{
  "compilerOptions": {
    "paths": {
      "@evidara/brand-shell": ["../../packages/brand-shell/src"]
    }
  }
}
```

In each consuming app's `vitest.config.ts` (so RTL tests that mount AppHeader / AppBar resolve the alias):

```ts
resolve: {
  alias: {
    "@evidara/brand-shell": path.resolve(__dirname, "../../packages/brand-shell/src"),
  },
},
```

Next.js (turbopack) already widens its `root` to the monorepo root for the existing token import, so it picks up the brand-shell source without further config.

## Why no Tailwind utility classes

The components ship inline styles only and reach colour through CSS custom properties (`var(--brand)`, `var(--brand-hover)`, `var(--brand-strong)`, `var(--foreground-muted)`). That keeps the package framework-agnostic — Tailwind v4's content scanner does not need to be widened to include `packages/brand-shell/`, and neither app's CSS bundle has to know the package exists.

## Tone

`<BrandLockup tone="light" />` (default) renders the wordmark in `--brand-strong` for surfaces with a light background (workspace). `<BrandLockup tone="dark" />` renders it in `currentColor` so dark/branded surfaces (admin's gradient header) can colour the wordmark via the parent's `color` value.

## Editor experience

The package keeps its own `node_modules` (just `react` + `@types/react` as devDependencies, installed via `npm install` inside `packages/brand-shell/`) so editors browsing this directory find React types. Real type-checking happens in each consuming app's `tsc --noEmit` run — the consumer's tsconfig pulls in this source via the path alias above.

## Tests and parity

Both apps own a parity test that scans their source and asserts the brand mark / wordmark markup is not re-implemented outside this package. See:

- `legal-search/frontend/src/__tests__/brand-shell-parity.test.ts`
- `platform-control/admin/src/__tests__/brand-shell-parity.test.ts`
