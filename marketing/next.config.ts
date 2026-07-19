import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static-first (ADR-0039). `output: "export"` emits plain HTML/CSS/JS into
  // `out/` with no Node server at runtime — the page is served by any static
  // file server (nginx sidecar / Traefik-fronted container). This is a
  // deliberate constraint, not an incidental one: a marketing page that
  // cannot execute server code cannot leak a secret, cannot be the entry
  // point to the control plane, and cannot fall over when the product does.
  //
  // Consequence: no `rewrites()`, no route handlers, no server actions. The
  // waitlist form posts directly to whatever `NEXT_PUBLIC_WAITLIST_ENDPOINT`
  // names (see src/lib/waitlist.ts), which today is nothing.
  output: "export",
  images: {
    // The static exporter cannot run the on-demand image optimizer.
    unoptimized: true,
  },
  turbopack: {
    // Widen the Turbopack root to the monorepo so globals.css can @import the
    // shared design tokens at styles/tokens/tokens.css. Same reasoning as
    // legal-search/frontend — see the long note there and #588.
    root: path.resolve(__dirname, ".."),
    // Widening the root also widens module resolution: the shared
    // `@evidara/shell` module at `styles/shell/` lives outside any npm
    // package, so Turbopack resolves ITS bare imports by walking up from
    // `styles/` and finds no `node_modules` at the repo root — the build then
    // fails with "Module not found: Can't resolve 'clsx'". Pin the shared
    // modules' runtime deps to this surface's own `node_modules`.
    //
    // `react` is deliberately NOT aliased here: Next resolves it itself (and
    // must, for the RSC react channel). See #588.
    resolveAlias: {
      clsx: "./node_modules/clsx",
      "lucide-react": "./node_modules/lucide-react",
      "tailwind-merge": "./node_modules/tailwind-merge",
    },
  },
};

export default nextConfig;
