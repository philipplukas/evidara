import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

test.describe("Frontend smoke journeys", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByPlaceholder(/search article, case, commentary, citation/i)).toBeVisible();
  });

  test("@smoke renders app shell and default query", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search article, case, commentary, citation/i);
    await expect(searchInput).toHaveValue(/.+/);
    await expect(page.getByText("Filters", { exact: true })).toHaveCount(1);
    await expect(page.getByText("Select a result")).toBeVisible();
  });

  test("@smoke submits search and focuses a result", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search article, case, commentary, citation/i);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");

    const firstResult = page.locator("article").first();
    await expect(firstResult).toBeVisible();
    await firstResult.click();
    await expect(page).toHaveURL(/item=/);
  });

  test("@smoke clears selection with Escape", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search article, case, commentary, citation/i);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);

    await page.keyboard.press("Escape");

    await expect(page).not.toHaveURL(/item=/);
    await expect(page.getByText("Select a result")).toBeVisible();
  });
});
