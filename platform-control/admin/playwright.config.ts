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
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      // NO `maxDiffPixelRatio` HERE — deliberately. See #611.
      //
      // The legal-search suite carried a project-level `maxDiffPixelRatio: 0.06`,
      // which on a 1600x900 full-page shot licenses ~86k pixels of drift. It stayed
      // green across a ~260px mislaid filter rail for ~3.5 months (#605), across a
      // replaced brand mark, and across the #674 filter-badge bug — in both
      // directions. A VRT suite that cannot go red is worse than none, because its
      // greenness is read as evidence.
      //
      // The default (undefined) allows zero differing pixels. If one snapshot
      // genuinely needs slack for platform font rendering, scope it to that single
      // `toHaveScreenshot` call with a comment justifying the number. Never widen
      // the default.
    },
  },
  use: {
    baseURL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    /*
     * A PRODUCTION BUILD, not `next dev`. Two reasons, one of them measured.
     *
     * `next dev` compiles a route on its first request. With two workers on a
     * cold cache, the first test to reach a data grid had to finish compile ->
     * serve -> hydrate -> fetch -> render inside Playwright's 5s `expect`
     * budget, and `retries: 0` turned every miss into a red job. Measured
     * 2026-09-19: `operator-usability.spec.ts:174` and
     * `preview-review-v2.spec.ts:134` — the two deepest locator chains in the
     * suite, both `row -> Cancel button` — failed on `main` itself at
     * f2611301, on a types-only PR, and on an untouched base commit, and
     * passed on every warm re-run. Three re-runs were spent on one PR
     * establishing that it was not a regression.
     *
     * The second reason stands on its own: `next dev` is not what ships. A
     * suite that only ever met the dev server was never testing the artifact.
     *
     * Local iteration cost is the build. `reuseExistingServer()` is the escape
     * hatch — start your own server, export the same E2E_RUN_ID, and the
     * identity nonce still proves it is yours.
     *
     * `next build` uses webpack, so the Tailwind resolution this file used to
     * pin with `--webpack` still holds: admin/node_modules, not the widened
     * monorepo root Turbopack would pick.
     */
    command: `npm run build && npm run start -- --port ${port}`,
    url: baseURL,
    // OPT-IN reuse. Defaulting this to true is how a lane's run silently
    // attached to another lane's dev server on :3000 and reported green
    // against a tree that did not contain its changes.
    reuseExistingServer: reuse,
    // A build plus a boot, not just a boot.
    timeout: 300_000,
    env: { E2E_RUN_ID: runId },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
