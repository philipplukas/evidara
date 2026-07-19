import { defineConfig } from "@playwright/test";
import {
  declareIdentityTargets,
  ensureRunId,
  reuseExistingServer,
} from "../../scripts/e2e/playwright-server-identity.mjs";

const externalBaseUrl = process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim();
const expectedControlPanelUrl = process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim();
const useRealBackend = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";
const ci = Boolean(process.env.CI);

// Every server this run starts is stamped with this nonce, and `globalSetup`
// refuses to run tests against a server that cannot echo it back. See
// scripts/e2e/playwright-server-identity.mjs.
const runId = ensureRunId();
const reuse = reuseExistingServer();

// Lanes run in parallel worktrees; each can claim its own ports. The ports are
// only a courtesy though — the identity check, not the port, is what proves
// the servers are ours. A stale container on 3101 already produced one false
// failure here (`width: 1`, the exact bug the lane had just fixed).
const frontendPort = Number(process.env.FRONTEND_E2E_PORT ?? 3101);
const adminPort = Number(process.env.ADMIN_E2E_PORT ?? 3100);
const frontendUrl = `http://localhost:${frontendPort}`;
const adminUrl = `http://localhost:${adminPort}`;

// The specs each re-derive these URLs from env, defaulting to the historical
// :3101/:3100. Once a lane can move its ports, that duplicated default is a
// second source of truth and silently breaks cross-surface navigation asserts.
// The config is what actually decides where the servers are, so it publishes
// the resolved URLs; the specs keep reading exactly the vars they already read.
// (`externalBaseUrl` above is captured before this, so the webServer decision
// is unaffected.)
const controlPanelUrl = expectedControlPanelUrl || adminUrl;
process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL = controlPanelUrl;
process.env.PLAYWRIGHT_ADMIN_BASE_URL = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || adminUrl;
process.env.PLAYWRIGHT_EXTERNAL_BASE_URL = externalBaseUrl || frontendUrl;

if (externalBaseUrl) {
  // We did not start it, so the nonce cannot match; verify the surface only.
  process.env.E2E_IDENTITY_EXTERNAL = "1";
  declareIdentityTargets([{ url: externalBaseUrl, surface: "legal-search-frontend" }]);
} else {
  declareIdentityTargets([
    { url: frontendUrl, surface: "legal-search-frontend" },
    { url: adminUrl, surface: "platform-control-admin" },
  ]);
}

/** Trace recording: off | on | retain-on-failure | on-first-retry (see Playwright docs). */
function traceMode(): "off" | "on" | "retain-on-failure" | "on-first-retry" {
  const raw = process.env.PLAYWRIGHT_TRACE?.trim().toLowerCase();
  if (raw === "off") {
    return "off";
  }
  if (raw === "on") {
    return "on";
  }
  if (raw === "on-first-retry" || raw === "on_first_retry") {
    return "on-first-retry";
  }
  if (raw === "retain-on-failure" || raw === "retain_on_failure") {
    return "retain-on-failure";
  }
  // Default: keep traces for failed tests (and use CI retry so flaky journeys self-heal).
  return "retain-on-failure";
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: ci ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      // Full-page Next dev + webfonts: small sub-pixel drift between runs; keep CI/local usable.
      maxDiffPixelRatio: 0.06,
    },
  },
  globalSetup: "../../scripts/e2e/playwright-server-identity.mjs",
  use: {
    baseURL: externalBaseUrl || frontendUrl,
    headless: true,
    screenshot: "only-on-failure",
    trace: traceMode(),
    video:
      process.env.PLAYWRIGHT_VIDEO === "on"
        ? "on"
        : process.env.PLAYWRIGHT_VIDEO === "off"
          ? "off"
          : "retain-on-failure",
  },
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          command: `env -u NO_COLOR npm run dev -- --webpack --port ${frontendPort}`,
          port: frontendPort,
          timeout: 120_000,
          // OPT-IN reuse (PLAYWRIGHT_REUSE_SERVER=1). Defaulting this to true
          // is how a run bound to a stale container on this port and reported
          // a bug it had already fixed.
          reuseExistingServer: reuse,
          env: {
            E2E_RUN_ID: runId,
            NEXT_PUBLIC_CONTROL_PANEL_URL: controlPanelUrl,
            NEXT_PUBLIC_DEFAULT_UI_PROFILE: "admin",
            ...(useRealBackend ? { NEXT_PUBLIC_API_URL: "http://localhost:3102" } : {}),
          },
        },
        {
          command: `env -u NO_COLOR npm run dev -- --webpack --port ${adminPort}`,
          cwd: "../../platform-control/admin",
          port: adminPort,
          timeout: 120_000,
          reuseExistingServer: reuse,
          env: {
            E2E_RUN_ID: runId,
            NEXT_PUBLIC_USER_ROLE: "viewer",
            NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "admin",
            NEXT_PUBLIC_LEGAL_SEARCH_URL: externalBaseUrl || frontendUrl,
          },
        },
      ],
});
