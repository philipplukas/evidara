import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { type Page, expect, test } from "@playwright/test";
import { mockAdminRunFlowApi } from "./helpers/mock-admin-api";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3000";
const ADMIN_BASE_URL = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3102";
const UI_PROFILE_COOKIE = "evidara-ui-profile";
const ADMIN_LOCAL_STORAGE_ROLE_KEY = "evidara_user_role";
const OUTPUT_DIR = "screenshot-pack";

async function saveScreenshot(page: Page, name: string) {
  await mkdir(OUTPUT_DIR, { recursive: true });
  await page.screenshot({
    path: join(OUTPUT_DIR, name),
    fullPage: true,
    animations: "disabled",
  });
}

test.describe("Canonical screenshot evidence pack", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.addCookies([
      {
        name: UI_PROFILE_COOKIE,
        value: "admin",
        url: new URL(LEGAL_SEARCH_BASE_URL).origin,
      },
    ]);
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await page.addInitScript(([key]) => {
      window.localStorage.setItem(key, "admin");
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
  });

  test("@screenshots captures legal-search and admin canonical surfaces", async ({ page }) => {
    await saveScreenshot(page, "cross-surface-header-navigation.png");
    await saveScreenshot(page, "legal-search-result-list.png");

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);

    await saveScreenshot(page, "legal-search-detail-panel.png");

    await page.goto(`${ADMIN_BASE_URL}/#/runs`);
    await expect(page.getByRole("button", { name: "Create Run" })).toBeVisible();
    await page.getByRole("button", { name: "Create Run" }).click();
    const createRunDialog = page.getByRole("dialog", { name: "Create Run" });
    await expect(createRunDialog).toBeVisible();
    await createRunDialog.getByRole("combobox", { name: /^Source$/ }).click();
    await page.getByRole("option", { name: "Swiss Federal Court" }).click();
    await createRunDialog.getByRole("combobox", { name: "Source version" }).click();
    await page.getByRole("option", { name: /2026.04.06/ }).click();
    await expect(page.getByText(/Run is blocked until preflight checks pass/i)).toBeVisible();
    await saveScreenshot(page, "admin-run-launch-preflight.png");

    await page.goto(`${ADMIN_BASE_URL}/#/runs/run_01/show`);
    await expect(page.getByRole("heading", { name: "Pipeline Health" })).toBeVisible();
    await expect(page.getByText("Operational status contract", { exact: false })).toBeVisible();
    await saveScreenshot(page, "admin-run-lifecycle-visibility.png");
  });
});
