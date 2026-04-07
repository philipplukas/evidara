import { defineConfig } from "@playwright/test";

const externalBaseUrl = process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim();
const adminBaseUrl = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim();
const expectedControlPanelUrl = process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim();

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: externalBaseUrl || "http://localhost:3101",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          command: "npm run dev -- --port 3101",
          port: 3101,
          timeout: 120_000,
          reuseExistingServer: true,
          env: {
            NEXT_PUBLIC_CONTROL_PANEL_URL: expectedControlPanelUrl || "http://localhost:3100",
            NEXT_PUBLIC_DEFAULT_UI_PROFILE: "admin",
          },
        },
        {
          command: "npm run dev -- --port 3100",
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
