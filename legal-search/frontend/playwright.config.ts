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
  // Playwright starts the frontend dev server automatically
  webServer: {
    command: "npm run dev -- --port 3000",
    port: 3000,
    timeout: 30_000,
    reuseExistingServer: true,
    env: {
      NEXT_PUBLIC_CONTROL_PANEL_URL: "http://localhost:3100",
    },
  },
});
