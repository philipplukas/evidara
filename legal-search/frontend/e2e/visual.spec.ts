import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

test.describe("Visual regressions", () => {
  test("workspace desktop shell matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article").first()).toBeVisible();

    // Anti-duplicate assertion: one scope-bar and one result title.
    // Pixel-diff tolerance (maxDiffPixelRatio) can hide structural regressions
    // like double-mounted components; this DOM-level check can't.
    await expect(page.getByText("Ausgangssuche", { exact: true })).toHaveCount(1);
    await expect(page.getByText(/Results for "Art\. 754/)).toHaveCount(1);

    await expect(page).toHaveScreenshot("workspace-desktop.png", {
      fullPage: true,
    });
  });

  test("workspace narrow shell matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await page.setViewportSize({ width: 430, height: 932 });
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article").first()).toBeVisible();

    await expect(page.getByText("Ausgangssuche", { exact: true })).toHaveCount(1);
    await expect(page.getByText(/Results for "Art\. 754/)).toHaveCount(1);

    await expect(page).toHaveScreenshot("workspace-mobile.png", {
      fullPage: true,
    });
  });

  test("app header matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("/");
    const header = page.getByRole("banner");
    await expect(header).toBeVisible();

    await expect(header).toHaveScreenshot("app-header.png");
  });

  test("results control region matches baseline", async ({ page }) => {
    await mockSearchApi(page, { richFacets: true });
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("/");
    const region = page.getByRole("region", { name: /Suchergebnisse/ });
    await expect(region).toBeVisible();

    await expect(region).toHaveScreenshot("results-control-region.png");
  });
});
