import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

// Use a wide viewport so the three-panel layout renders fully
test.use({ viewport: { width: 1600, height: 900 } });

test.describe("Workspace Panels", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
  });

  test("renders three resizable panels and two handles", async ({ page }) => {
    await expect(page.locator("[data-panel]")).toHaveCount(3);
    await expect(page.getByRole("separator")).toHaveCount(2);
    await expect(page.getByText("Filters", { exact: true })).toHaveCount(1);
  });

  test("loads deterministic result card content in center panel", async ({ page }) => {
    await expect(page.getByText("Result for Bundesgericht")).toBeVisible();
    await expect(page.getByText("2026-04-03")).toBeVisible();
  });

  test("detail panel transitions from empty to selected item", async ({ page }) => {
    await expect(page.getByText("Select a result")).toBeVisible();

    await page.getByText("Result for Bundesgericht").click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(page.getByText("Mocked detail title")).toBeVisible();
  });
});
