import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

/** Must match `EVIDARA_UI_PROFILE_COOKIE` in `src/lib/control-plane-entry.ts`. */
const UI_PROFILE_COOKIE = "evidara-ui-profile";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const CONTROL_PANEL_LABEL = /control panel|kontrollbereich|panneau de contr[oô]le/i;

/** Playwright `webServer`: admin dev server with non-admin role (`playwright.config.ts`). */
const ADMIN_CONTRACT_BASE_URL = "http://localhost:3102";

test.describe("@contract RBAC cross-surface (legal-search header + admin denial)", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("admin profile shows control panel entry when URL is configured", async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    await expect(controlPanelLink).toBeVisible();
    await expect(controlPanelLink).toHaveAttribute("href", "http://localhost:3100");
  });

  test("standard profile does not show control panel entry when URL is configured", async ({
    page,
    context,
  }) => {
    await context.addCookies([
      {
        name: UI_PROFILE_COOKIE,
        value: "standard",
        url: "http://localhost:3000",
      },
    ]);
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    await expect(page.getByRole("link", { name: CONTROL_PANEL_LABEL })).toHaveCount(0);
  });

  test("direct admin URL shows denial UX for non-admin role (403 messaging + recovery)", async ({
    page,
  }) => {
    await page.goto(`${ADMIN_CONTRACT_BASE_URL}/`);
    await expect(page.getByText(/403 forbidden/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /access denied/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /return to legal search/i })).toBeVisible();
  });
});
