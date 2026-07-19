import { defineConfig } from "@playwright/test";
import {
  declareIdentityTargets,
  ensureRunId,
  reuseExistingServer,
} from "../../scripts/e2e/playwright-server-identity.mjs";

// Every server this run starts is stamped with this nonce, and `globalSetup`
// refuses to run tests against a server that cannot echo it back. See
// scripts/e2e/playwright-server-identity.mjs.
const runId = ensureRunId();
const reuse = reuseExistingServer();

// Lanes run in parallel worktrees; each can claim its own port. The port is
// only a courtesy though — the identity check, not the port, is what proves
// the server is ours.
const port = Number(process.env.ADMIN_E2E_PORT ?? 3000);
const baseURL = `http://localhost:${port}`;

declareIdentityTargets([{ url: baseURL, surface: "platform-control-admin" }]);

/**
 * Port is overridable via `ADMIN_E2E_PORT` (default 3000, which is what CI uses).
 *
 * `reuseExistingServer` adopts a dev server already listening on the port rather
 * than replacing it — convenient locally, and a silent trap when two git
 * worktrees of this repo are worked on at once: the second run adopts the *first
 * worktree's build* and reports results against code that is not the code under
 * test. It is therefore **opt-in** (`reuseExistingServer()`), not defaulted on,
 * and the identity nonce above is what actually proves the server is ours — a
 * per-worktree port is only a courtesy.
 */

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  globalSetup: "../../scripts/e2e/playwright-server-identity.mjs",
  use: {
    baseURL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    // Webpack dev mode resolves Tailwind from admin/node_modules while
    // Turbopack's widened monorepo root resolves CSS from platform-control.
    command: `npm run dev -- --webpack --port ${port}`,
    url: baseURL,
    // OPT-IN reuse. Defaulting this to true is how a lane's run silently
    // attached to another lane's dev server on :3000 and reported green
    // against a tree that did not contain its changes.
    reuseExistingServer: reuse,
    timeout: 60_000,
    env: { E2E_RUN_ID: runId },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
