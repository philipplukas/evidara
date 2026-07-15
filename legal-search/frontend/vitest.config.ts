import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
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
    // Without it, `styles/ui` binds to a foreign React and every component
    // rendering <StatusBadge> dies with
    // "Cannot read properties of null (reading 'useContext')". See #588.
    dedupe: ["react", "react-dom", "lucide-react", "clsx", "tailwind-merge"],
  },
  // Vite's dev server only serves files from inside the project root by
  // default; the shared `@evidara/ui` parity test lives at the monorepo
  // root under `styles/ui/`, so widen the allow list to include it.
  server: {
    fs: {
      allow: [path.resolve(__dirname, "../..")],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    // Include the shared `@evidara/ui` parity test once on the workspace
    // surface. The test scans file contents (no alias resolution), so a
    // single run is sufficient — admin's vitest does not duplicate it.
    include: ["src/**/*.test.{ts,tsx}", "../../styles/ui/**/*.test.{ts,tsx}"],
  },
});
