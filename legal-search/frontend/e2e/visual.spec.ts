import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

test.describe("Visual regressions", () => {
  test("workspace desktop shell matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    await expect(page).toHaveScreenshot("workspace-desktop.png", {
      fullPage: true,
      animations: "disabled",
    });
  });

  test("workspace narrow shell matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await page.setViewportSize({ width: 430, height: 932 });
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    await expect(page).toHaveScreenshot("workspace-mobile.png", {
      fullPage: true,
      animations: "disabled",
    });
  });
});
