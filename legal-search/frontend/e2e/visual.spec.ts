import { expect, test } from "@playwright/test";
import { mockAdminRunFlowApi } from "./helpers/mock-admin-api";
import { mockSearchApi } from "./helpers/mock-api";

const ADMIN_BASE_URL = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3100";
const ADMIN_LOCAL_STORAGE_ROLE_KEY = "evidara_user_role";

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

  // Net-new tracked coverage for the admin run-detail v2 layout introduced in
  // PR #413 ("Run overview" quadrant: `Why this matters` primary card plus
  // three subordinate cards). The screenshot-pack capture at
  // `screenshot-pack.spec.ts:~274` is a scratch artefact (gitignored), not
  // committed coverage — a layout regression in this quadrant would slip past
  // CI without this baseline. Navigation + wait points mirror that capture so
  // the framing stays comparable.
  test("admin run-detail v2 — primary decision hierarchy matches baseline", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await page.addInitScript(([key]) => {
      window.localStorage.setItem(key, "admin");
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
    await page.setViewportSize({ width: 1600, height: 900 });

    await page.goto(`${ADMIN_BASE_URL}/#/runs-v2/run_01`, { waitUntil: "load" });
    await expect(page.getByRole("heading", { name: /Decision support/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Run run_01/ })).toBeVisible();
    // `RunDetailSectionsV2` renders collapsed accordion items below the
    // metadata grid. Wait for the `Provider Jobs` trigger so the capture
    // includes the full lifecycle stack (matches screenshot-pack framing).
    await expect(page.getByRole("button", { name: /Provider Jobs/ })).toBeVisible();

    await expect(page).toHaveScreenshot("admin-run-detail-v2.png", {
      fullPage: true,
    });
  });
});
