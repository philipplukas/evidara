import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Widen the Turbopack root to the monorepo so globals.css can
    // @import the shared design tokens at styles/tokens/tokens.css.
    //
    // Without this, `next dev` panics at compile time with
    // `FileSystemPath("").join("../../styles/tokens/tokens.css") leaves
    // the filesystem root` and returns HTTP 500. `next build` succeeds
    // (prod CSS bundling takes a different path), so the bug hides
    // from local production checks and only surfaces when Playwright's
    // webServer: `npm run dev` crashes. Must match the Docker build
    // context root (see Dockerfile).
    root: path.resolve(process.cwd(), "../.."),
    // Widening the root (above) also widens module resolution: the shared
    // `@evidara/ui` module at `styles/ui/` lives outside any npm package, so
    // Turbopack resolves ITS bare imports by walking up from `styles/` and
    // finds no `node_modules` at the repo root — the build then fails with
    // "Module not found: Can't resolve 'clsx'". Pin the shared modules'
    // runtime deps to this surface's own `node_modules`.
    //
    // `react` is deliberately NOT aliased here: Next resolves it itself (and
    // must, for the RSC react channel). See #588.
    //
    // Paths are relative to THIS project directory (where next.config.ts
    // lives), not to `root` — Turbopack treats resolveAlias values as module
    // requests, so an absolute path is rejected.
    resolveAlias: {
      clsx: "./node_modules/clsx",
      "lucide-react": "./node_modules/lucide-react",
      "tailwind-merge": "./node_modules/tailwind-merge",
    },
  },
};

export default nextConfig;
