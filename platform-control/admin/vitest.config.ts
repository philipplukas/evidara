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
      // Pin React + lucide-react to admin's own `node_modules`. Without
      // this, when `@evidara/ui`'s `StatusBadge.tsx` imports `react` or
      // `lucide-react`, Vite walks up from `styles/ui/` and finds the
      // monorepo-root `node_modules` symlink (created by the
      // `ensure-monorepo-shared-modules` postinstall, which points at
      // whichever surface installed first). That can route React to a
      // *different* `node_modules` than the rest of the admin tree,
      // producing two React instances and the "Invalid hook call" error
      // when admin renders `<StatusBadge>` inside a test. Pinning these
      // here keeps every dual-surface test on a single React.
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
      "react/jsx-runtime": path.resolve(__dirname, "node_modules/react/jsx-runtime.js"),
      "lucide-react": path.resolve(__dirname, "node_modules/lucide-react"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
