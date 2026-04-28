import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@evidara/tokens": path.resolve(__dirname, "../../styles/tokens/tokens"),
    },
    // Mirrors `preserveSymlinks: true` in tsconfig.json. The shared
    // `@evidara/brand-shell` package is installed as a `file:` symlink
    // at `node_modules/@evidara/brand-shell`; without preserving the
    // symlink path, Vite resolves to `packages/brand-shell/src/*` and
    // walks up from there looking for `react`, missing this app's copy.
    preserveSymlinks: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
