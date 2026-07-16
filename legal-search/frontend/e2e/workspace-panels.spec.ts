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

  // Regression guard for the react-resizable-panels v4 units bug: a bare-number
  // size is PIXELS in v4, so `minSize={25}` / `resize(32)` collapsed the filter
  // rail to ~28px and the detail panel to ~32px. The structural checks above
  // still pass at those widths (the panels exist and their text is in the DOM),
  // which is exactly why they missed it. Assert real rendered geometry instead.
  test("filter rail and detail panel render at usable widths, not px slivers", async ({ page }) => {
    const panels = page.locator("[data-panel]");
    // Filter rail is ~18% of the 1600px row (≈288px); a pixel-collapsed rail is ~28px.
    const filterBox = await panels.nth(0).boundingBox();
    expect(filterBox?.width ?? 0).toBeGreaterThan(150);

    await page.getByText("Result for Bundesgericht").click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(page.getByText("Mocked detail title")).toBeVisible();
    // Detail panel is ~32% (≈512px); a pixel-collapsed panel is ~32px.
    const detailBox = await panels.nth(2).boundingBox();
    expect(detailBox?.width ?? 0).toBeGreaterThan(300);
  });
});
