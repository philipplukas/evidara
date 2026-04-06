import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { type Page, expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3000";
const UI_PROFILE_COOKIE = "evidara-ui-profile";
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
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
  });

  test("@screenshots captures legal-search canonical surfaces", async ({ page }) => {
    await saveScreenshot(page, "cross-surface-header-navigation.png");
    await saveScreenshot(page, "legal-search-result-list.png");

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);

    await saveScreenshot(page, "legal-search-detail-panel.png");
  });
});
