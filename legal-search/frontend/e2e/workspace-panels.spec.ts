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

  // The UI renders in German (`de` is the default locale) and the mock builds
  // the result title from the query. These assertions had drifted to English
  // copy and an ISO date that the UI has not produced for some time, so the
  // whole spec was red before any of the fixes in this change.
  const RESULT_TITLE = "Result for Art. 754 OR Verantwortlichkeit";

  test("renders three resizable panels and two handles", async ({ page }) => {
    await expect(page.locator("[data-panel]")).toHaveCount(3);
    await expect(page.getByRole("separator")).toHaveCount(2);
    await expect(
      page.locator("[data-panel]").first().getByText("Filter", { exact: true }),
    ).toHaveCount(1);
  });

  test("loads deterministic result card content in center panel", async ({ page }) => {
    await expect(page.getByText(RESULT_TITLE)).toBeVisible();
    await expect(page.getByText("03.04.2026")).toBeVisible();
  });

  test("detail panel transitions from empty to selected item", async ({ page }) => {
    await expect(page.getByText("Kein Ergebnis ausgewählt")).toBeVisible();

    await page.getByText(RESULT_TITLE).click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(
      page.getByText("BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats"),
    ).toBeVisible();
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

    await page.getByText(RESULT_TITLE).click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(
      page.getByText("BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats"),
    ).toBeVisible();
    // Detail panel is ~32% (≈512px); a pixel-collapsed panel is ~32px.
    const detailBox = await panels.nth(2).boundingBox();
    expect(detailBox?.width ?? 0).toBeGreaterThan(300);
  });

  // Regression guard for #679: both separators measured exactly 1 physical
  // pixel wide, so the drag handle was practically unhittable with a mouse and
  // unreachable by touch — well under WCAG 2.5.5 (44px) and 2.5.8 (24px).
  // Geometry, not pixels: a 1px handle is invisible to screenshot diffing
  // (that is the #611 lesson), but a bounding box states it outright.
  test("resize handles expose a hittable target, not a 1px sliver", async ({ page }) => {
    const separators = page.getByRole("separator");
    await expect(separators).toHaveCount(2);

    for (const separator of await separators.all()) {
      const box = await separator.boundingBox();
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(16);
      // Full-height along the panel row — the target is a strip, not a dot.
      expect(box?.height ?? 0).toBeGreaterThan(200);
    }
  });

  // Regression guard for #610: dragging the rail below `minSize` collapsed it
  // to a sliver that rendered the *full* FilterPanel clipped into unreadable
  // fragments ("FILT", "S C", "A C"). Collapsed must render the icon rail with
  // an expand affordance instead — and expanding must restore a usable width.
  test("collapsing the filter rail renders an icon rail that can be expanded", async ({ page }) => {
    const filterPanel = page.locator("[data-panel]").first();
    const separator = page.getByRole("separator").first();

    const separatorBox = await separator.boundingBox();
    if (!separatorBox) throw new Error("filter rail separator has no bounding box");

    // Drag the handle far left, past `minSize`, so the rail collapses.
    await page.mouse.move(
      separatorBox.x + separatorBox.width / 2,
      separatorBox.y + separatorBox.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(0, separatorBox.y + separatorBox.height / 2, { steps: 10 });
    await page.mouse.up();

    const expandButton = filterPanel.getByRole("button", { name: /Filterbereich einblenden/ });
    await expect(expandButton).toBeVisible();
    // The clipped full panel must be gone, not merely narrow.
    await expect(filterPanel.getByText("Keine Filter verfügbar")).toHaveCount(0);

    const collapsedBox = await filterPanel.boundingBox();
    expect(collapsedBox?.width ?? 0).toBeLessThan(100);

    await expandButton.click();
    await expect(expandButton).toHaveCount(0);
    const expandedBox = await filterPanel.boundingBox();
    expect(expandedBox?.width ?? 0).toBeGreaterThan(150);
  });
});
