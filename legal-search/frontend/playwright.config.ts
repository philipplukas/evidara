import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "npm run dev -- --port 3000",
      port: 3000,
      timeout: 120_000,
      reuseExistingServer: true,
      env: {
        NEXT_PUBLIC_CONTROL_PANEL_URL: "http://localhost:3100",
        NEXT_PUBLIC_DEFAULT_UI_PROFILE: "admin",
      },
    },
    {
      command: "npm run dev -- --port 3102",
      cwd: "../../platform-control/admin",
      port: 3102,
      timeout: 120_000,
      reuseExistingServer: true,
      env: {
        NEXT_PUBLIC_USER_ROLE: "viewer",
        NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "admin",
        NEXT_PUBLIC_LEGAL_SEARCH_URL: "http://localhost:3000",
      },
    },
  ],
});
