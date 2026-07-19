import { defineConfig } from "@playwright/test";

/**
 * Port is overridable via `ADMIN_E2E_PORT` (default 3000, which is what CI uses).
 *
 * `reuseExistingServer: true` means a dev server already listening on the port
 * is adopted rather than replaced — which is the right behaviour locally, and a
 * silent trap when two git worktrees of this repo are worked on at once: the
 * second run adopts the *first worktree's build* and reports failures against
 * code that is not the code under test. Setting the port per worktree gives each
 * one its own server.
 */
const PORT = process.env.ADMIN_E2E_PORT ?? "3000";
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: BASE_URL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    // Webpack dev mode resolves Tailwind from admin/node_modules while
    // Turbopack's widened monorepo root resolves CSS from platform-control.
    command: `npm run dev -- --webpack --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
