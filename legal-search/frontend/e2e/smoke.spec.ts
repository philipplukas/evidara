import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER = /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const FILTERS_LABEL = /filters|filter|filtres/i;

test.describe("Frontend smoke journeys", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();
  });

  test("@smoke renders app shell and default query", async ({ page }) => {
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await expect(searchInput).toHaveValue(/.+/);
    await expect(page.getByText(FILTERS_LABEL, { exact: true })).toHaveCount(1);
    await expect(page.getByText("Select a result")).toBeVisible();
  });

  test("@smoke submits search and focuses a result", async ({ page }) => {
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");

    const firstResult = page.locator("article").first();
    await expect(firstResult).toBeVisible();
    await firstResult.click();
    await expect(page).toHaveURL(/item=/);
  });

  test("@smoke clears selection with Escape", async ({ page }) => {
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);

    await page.keyboard.press("Escape");

    await expect(page).not.toHaveURL(/item=/);
    await expect(page.getByText("Select a result")).toBeVisible();
  });
});
