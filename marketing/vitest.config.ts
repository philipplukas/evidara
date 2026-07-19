import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@evidara/tokens": path.resolve(__dirname, "../styles/tokens/tokens"),
      "@evidara/shell": path.resolve(__dirname, "../styles/shell"),
    },
    // The shared `@evidara/*` modules live at `styles/`, outside any npm
    // package. Vite resolves a module's bare imports relative to the IMPORTING
    // file, so `styles/shell/BrandMark.tsx`'s `react` import would be resolved
    // by walking UP from `styles/` — escaping this surface entirely. `dedupe`
    // forces these specifiers to resolve from THIS surface's root instead,
    // guaranteeing a single React instance shared by the app code and the
    // shared modules.
    //
    // Without it, `styles/shell` binds to a foreign React and every component
    // rendering <BrandMark> dies with
    // "Cannot read properties of null (reading 'useContext')". See #588.
    dedupe: ["react", "react-dom", "lucide-react", "clsx", "tailwind-merge"],
  },
  // Vite's dev server only serves files from inside the project root by
  // default; the shared modules live at the monorepo root under `styles/`.
  server: {
    fs: {
      allow: [path.resolve(__dirname, "..")],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
