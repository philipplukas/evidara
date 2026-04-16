import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Extend the Turbopack root up to the monorepo root so globals.css
    // can @import the shared design tokens from contracts/design-tokens.
    root: path.resolve(process.cwd(), "../.."),
  },
};

export default nextConfig;
