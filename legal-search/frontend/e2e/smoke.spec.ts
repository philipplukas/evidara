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
    await expect(searchInput).toHaveValue("Bundesgericht");
    await expect(page.getByText("Filters", { exact: true })).toHaveCount(1);
    await expect(page.getByText("Select a result")).toBeVisible();
  });

  test("@smoke submits search and focuses a result", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search article, case, commentary, citation/i);
    await searchInput.fill("governance");
    await searchInput.press("Enter");

    const resultTitle = page.getByText("Result for governance");
    await expect(resultTitle).toBeVisible();

    await resultTitle.click();

    await expect(page).toHaveURL(/item=decision-1/);
  });

  test("@smoke clears selection with Escape", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search article, case, commentary, citation/i);
    await searchInput.fill("governance");
    await searchInput.press("Enter");
    await page.getByText("Result for governance").click();
    await expect(page).toHaveURL(/item=decision-1/);

    await page.keyboard.press("Escape");

    await expect(page).not.toHaveURL(/item=/);
    await expect(page.getByText("Select a result")).toBeVisible();
  });
});
