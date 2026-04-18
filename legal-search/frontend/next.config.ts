import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy API calls to the BFF during local development.
  // The Orval-generated client uses relative URLs (/v1/...),
  // so Next.js rewrites route them to the NestJS API.
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3102";
    return [
      {
        source: "/v1/:path*",
        destination: `${apiBase}/v1/:path*`,
      },
    ];
  },
  turbopack: {
    // Widen the Turbopack root to the monorepo so globals.css can
    // @import the shared design tokens at styles/tokens/tokens.css.
    //
    // Without this, `next dev` panics at compile time with
    // `FileSystemPath("").join("../../styles/tokens/tokens.css") leaves
    // the filesystem root` and returns HTTP 500. `next build` succeeds
    // (prod CSS bundling takes a different path), so the bug hides
    // from local production checks and only surfaces when Playwright's
    // webServer: `npm run dev` crashes — frontend-visual-regression
    // and interaction-flow-evidence then screenshot the 500 page.
    // Must match the Docker build context root (see Dockerfile).
    root: path.resolve(__dirname, "../.."),
  },
};

export default nextConfig;
