import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER = /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const FILTERS_LABEL = /filters|filter|filtres/i;
const CONTROL_PANEL_LABEL = /control panel|kontrollbereich|panneau de contr[oô]le/i;
const EXPECTED_CONTROL_PANEL_URL =
  process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim() || "http://localhost:3100";
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3101";
const USE_REAL_BACKEND = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";
const UI_PROFILE_COOKIE = "evidara-ui-profile";

test.describe("Frontend smoke journeys", () => {
  test.beforeEach(async ({ page, context }) => {
    await context.addCookies([
      {
        name: UI_PROFILE_COOKIE,
        value: "admin",
        url: new URL(LEGAL_SEARCH_BASE_URL).origin,
      },
    ]);
    if (!USE_REAL_BACKEND) {
      await mockSearchApi(page);
    }
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

  test("@smoke exposes control panel entrypoint in header", async ({ page }) => {
    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    await expect(controlPanelLink).toBeVisible();
    await expect(controlPanelLink).toHaveAttribute("href", EXPECTED_CONTROL_PANEL_URL);
  });

  test("@smoke @real-api applies filters against live /v1/search", async ({ page }) => {
    test.skip(!USE_REAL_BACKEND, "real backend mode is opt-in via PLAYWRIGHT_USE_REAL_BACKEND=true");

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");

    const initialRequest = await page.waitForResponse(
      (response) => response.url().includes("/v1/search?") && response.request().method() === "GET",
    );
    const initialUrl = new URL(initialRequest.url());
    const beforeCount = await page.locator("article").count();

    const firstCheckboxRow = page.locator('label:has(input[type="checkbox"])').first();
    await expect(firstCheckboxRow).toBeVisible();
    const countText = (await firstCheckboxRow.locator("span").last().textContent())?.trim() ?? "";
    const expectedUpperBound = Number.parseInt(countText.replace(/[^\d]/g, ""), 10);
    await firstCheckboxRow.click();

    const filteredRequest = await page.waitForResponse(
      (response) => response.url().includes("/v1/search?") && response.request().method() === "GET",
    );
    const filteredUrl = new URL(filteredRequest.url());
    await expect.poll(async () => page.locator("article").count()).not.toBe(beforeCount);
    const afterCount = await page.locator("article").count();

    expect(filteredUrl.search).not.toEqual(initialUrl.search);
    if (!Number.isNaN(expectedUpperBound)) {
      expect(afterCount).toBeLessThanOrEqual(expectedUpperBound);
    }
  });
});
