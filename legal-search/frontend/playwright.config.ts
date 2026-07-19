import { defineConfig } from "@playwright/test";

const externalBaseUrl = process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim();
const expectedControlPanelUrl = process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim();
const useRealBackend = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";
const ci = Boolean(process.env.CI);

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
      // NO `maxDiffPixelRatio` HERE — deliberately. See #611.
      //
      // A project-level `maxDiffPixelRatio: 0.06` used to sit on this object,
      // so all 15 `toHaveScreenshot` calls in `e2e/visual.spec.ts` silently
      // inherited a 6% tolerance. On a 1600x900 full-page shot that is ~86k
      // pixels of licensed drift — enough to absorb an entire mislaid layout
      // region. It did exactly that: the filter rail rendered ~260px too
      // narrow for ~3.5 months (#605) and this suite stayed green through the
      // bug AND through its fix, because the tolerance ate the difference in
      // both directions. A VRT suite that cannot go red is worse than none,
      // because its greenness is read as evidence.
      //
      // The default (undefined) means zero differing pixels are allowed. If a
      // single snapshot genuinely needs slack for platform font rendering,
      // scope it to that one `toHaveScreenshot` call with a comment
      // justifying the specific number — never widen the default again.
    },
  },
  use: {
    baseURL: externalBaseUrl || "http://localhost:3101",
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
          command: "env -u NO_COLOR npm run dev -- --webpack --port 3101",
          port: 3101,
          timeout: 120_000,
          reuseExistingServer: true,
          env: {
            NEXT_PUBLIC_CONTROL_PANEL_URL: expectedControlPanelUrl || "http://localhost:3100",
            NEXT_PUBLIC_DEFAULT_UI_PROFILE: "admin",
            ...(useRealBackend ? { NEXT_PUBLIC_API_URL: "http://localhost:3102" } : {}),
          },
        },
        {
          command: "env -u NO_COLOR npm run dev -- --webpack --port 3100",
          cwd: "../../platform-control/admin",
          port: 3100,
          timeout: 120_000,
          reuseExistingServer: true,
          env: {
            NEXT_PUBLIC_USER_ROLE: "viewer",
            NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "admin",
            NEXT_PUBLIC_LEGAL_SEARCH_URL: externalBaseUrl || "http://localhost:3101",
          },
        },
      ],
});
