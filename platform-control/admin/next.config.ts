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
  },
};

export default nextConfig;
