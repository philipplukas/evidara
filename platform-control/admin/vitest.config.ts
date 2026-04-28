import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
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
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
