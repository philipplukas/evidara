# `@evidara/brand-shell`

Shared brand chrome — the gradient `E` mark, the `Evidara` wordmark lockup, and a thin `<BrandHeader>` slot wrapper — consumed by both `legal-search/frontend` and `platform-control/admin`.

This package exists because the two surfaces had been re-implementing the brand mark and wordmark in two visually divergent forms. After the late-April 2026 brand-parity track (#486–#491) routed both surfaces through the same token ladder, the brand chrome itself was the last visible "two products" tell. This package consolidates that single piece into one source of truth.

## Scope (and what stays out)

- **In scope:** `<BrandMark>` (the gradient "E"), `<BrandLockup>` (mark + wordmark + optional sub-label), `<BrandHeader>` (a thin wrapper around `<header>` for shared semantics; each surface supplies its own className/style for surface-specific chrome).
- **Not in scope:** buttons, inputs, focus rings, pills, badges, narrative cards, operator cards. Those primitives stay in their respective apps under ADR-0016 and ADR-0027 ("two products, shared brand"). This package is specifically about the lockup that crosses both surfaces.

## How both apps consume it

Each consuming app declares a local `file:` dependency:

```jsonc
// legal-search/frontend/package.json
// platform-control/admin/package.json
{
  "dependencies": {
    "@evidara/brand-shell": "file:../../packages/brand-shell"
  }
}
```

`npm install` creates `node_modules/@evidara/brand-shell` as a symlink to this directory, so changes here are picked up immediately without a re-install. React (the package's only runtime dependency) is satisfied by the consuming app's own `react` install via the `peerDependencies` declaration.

### `preserveSymlinks: true` is required

The package is a symlink under each app's `node_modules`. By default both TypeScript and Vite follow the symlink to its real path (`packages/brand-shell/src/*`) and walk up *from there* looking for `react` — which fails because `packages/brand-shell` has no `node_modules`. Both apps therefore set `preserveSymlinks: true`:

- `tsconfig.json` → `compilerOptions.preserveSymlinks: true`
- `vitest.config.ts` → `resolve.preserveSymlinks: true`

With that flag set, the resolver walks up from the symlinked location (`<app>/node_modules/@evidara/brand-shell/src/`) and finds `<app>/node_modules/react`. Next.js / Turbopack handle this correctly out of the box without extra config.

## Why no Tailwind utility classes

The components ship inline styles only and reach colour through CSS custom properties (`var(--brand)`, `var(--brand-hover)`, `var(--brand-strong)`, `var(--foreground-muted)`). That keeps the package framework-agnostic — Tailwind v4's content scanner does not need to be widened to include `packages/brand-shell/`, and neither app's CSS bundle has to know the package exists.

## Tone

`<BrandLockup tone="light" />` (default) renders the wordmark in `--brand-strong` for surfaces with a light background (workspace). `<BrandLockup tone="dark" />` renders it in `currentColor` so dark/branded surfaces (admin's gradient header) can colour the wordmark via the parent's `color` value.

## Tests and parity

Both apps own a parity test that scans their source and asserts the brand mark / wordmark markup is not re-implemented outside this package. See:

- `legal-search/frontend/src/__tests__/brand-shell-parity.test.ts`
- `platform-control/admin/src/__tests__/brand-shell-parity.test.ts`
