#!/usr/bin/env node
/**
 * Ensure a `<repo>/node_modules` symlink exists so that the shared modules
 * under `styles/` (currently `@evidara/tokens`, `@evidara/shell`, and
 * `@evidara/ui`) resolve their bare-package imports during TypeScript
 * compilation.
 *
 * Why: per ADR-0028 / ADR-0026 P6, shared cross-surface modules live under
 * `styles/` and are exposed to each surface via a `tsconfig.json` `paths`
 * alias. When a shared module gains real code (e.g. `@evidara/ui`'s
 * `StatusBadge.tsx` imports `react`, `clsx`, `lucide-react`), the surface's
 * `tsc --noEmit` follows the import into `styles/ui/` and tries to resolve
 * those bare specifiers via Node module resolution. With `bundler` /
 * `nodenext` resolution, tsc walks parent directories of the imported file
 * looking for `node_modules`. There is no `node_modules` at the monorepo
 * root because the repo is not an npm workspace today (intentional —
 * ADR-0026 P6 defers workspace conversion). This script bridges the gap by
 * symlinking `<repo>/node_modules` to whichever surface ran `npm install`
 * first; both surfaces install the same React / lucide / clsx /
 * tailwind-merge versions, so the symlinked tree is sufficient for
 * type-checking.
 *
 * The symlink is `.gitignore`-covered (root `.gitignore` ignores
 * `node_modules/`), idempotent, and a no-op if it already exists. It does
 * not affect runtime: each surface continues to resolve bare imports
 * through its own `node_modules`. Vitest, Next.js Turbopack, and Biome all
 * use their own resolvers.
 *
 * If the consuming surface's `node_modules` is missing (CI hasn't
 * installed yet, or this script ran before `npm install` finished), the
 * script exits successfully without creating a symlink. The next
 * postinstall pass will create it.
 */

import { existsSync, lstatSync, readlinkSync, symlinkSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const repoNodeModules = resolve(repoRoot, "node_modules");

// Order: prefer the surface whose `npm install` is most likely to be
// running this script. The first existing `node_modules` wins.
const candidates = [
  resolve(repoRoot, "legal-search/frontend/node_modules"),
  resolve(repoRoot, "platform-control/admin/node_modules"),
];

const target = candidates.find((p) => existsSync(p));

if (!target) {
  console.log(
    "[shared-modules] no surface has installed node_modules yet; nothing to link.",
  );
  process.exit(0);
}

if (existsSync(repoNodeModules)) {
  const stat = lstatSync(repoNodeModules);
  if (stat.isSymbolicLink()) {
    const current = readlinkSync(repoNodeModules);
    const currentAbs = resolve(repoRoot, current);
    if (currentAbs === target) {
      // Already correctly linked.
      process.exit(0);
    }
    console.log(
      `[shared-modules] ${repoNodeModules} already symlinked to ${current}; leaving alone.`,
    );
    process.exit(0);
  }
  console.log(
    `[shared-modules] ${repoNodeModules} exists and is not a symlink; leaving alone.`,
  );
  process.exit(0);
}

symlinkSync(relative(repoRoot, target), repoNodeModules, "dir");
console.log(
  `[shared-modules] linked ${repoNodeModules} -> ${relative(repoRoot, target)}`,
);
