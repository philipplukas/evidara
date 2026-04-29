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
    },
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
