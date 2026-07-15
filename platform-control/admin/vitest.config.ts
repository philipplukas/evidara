import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror the `tsconfig.json` path aliases so vitest fails loudly if
      // either drifts. The shared modules live at the monorepo root under
      // `styles/`; both surfaces consume them via the same alias names.
      "@evidara/tokens": path.resolve(__dirname, "../../styles/tokens/tokens"),
      "@evidara/ui": path.resolve(__dirname, "../../styles/ui"),
      "@evidara/shell": path.resolve(__dirname, "../../styles/shell"),
    },
    // The shared `@evidara/*` modules live at `styles/`, outside any npm
    // package. Vite resolves a module's bare imports relative to the
    // IMPORTING file, so `styles/ui/StatusBadge.tsx`'s `react` /
    // `lucide-react` imports would be resolved by walking UP from `styles/`
    // — escaping this workspace entirely. `dedupe` forces these specifiers
    // to resolve from THIS surface's root instead, guaranteeing a single
    // React instance shared by the app code and the shared modules.
    //
    // This replaces a hand-rolled set of absolute `node_modules` aliases:
    // `dedupe` covers subpath imports (`react/jsx-runtime`) for free, and
    // the frontend now carries the identical guard. See #588.
    dedupe: ["react", "react-dom", "lucide-react", "clsx", "tailwind-merge"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
