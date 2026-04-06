import type { BrowserContext } from "@playwright/test";
import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

/** Must match `EVIDARA_UI_PROFILE_COOKIE` in `src/lib/control-plane-entry.ts`. */
const UI_PROFILE_COOKIE = "evidara-ui-profile";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const CONTROL_PANEL_LABEL = /control panel|kontrollbereich|panneau de contr[oô]le/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3000";
const EXPECTED_CONTROL_PANEL_URL =
  process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim() || "http://localhost:3100";

/** Playwright `webServer`: admin dev server with non-admin role (`playwright.config.ts`). */
const ADMIN_CONTRACT_BASE_URL =
  process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3102";
const ADMIN_LOCAL_STORAGE_ROLE_KEY = "evidara_user_role";

async function setUiProfileCookie(context: BrowserContext, profile: "admin" | "standard") {
  await context.addCookies([
    {
      name: UI_PROFILE_COOKIE,
      value: profile,
      url: new URL(LEGAL_SEARCH_BASE_URL).origin,
    },
  ]);
}

test.describe("@contract RBAC cross-surface (legal-search header + admin denial)", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("admin profile shows control panel entry when URL is configured", async ({ page }) => {
    await setUiProfileCookie(page.context(), "admin");
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    await expect(controlPanelLink).toBeVisible();
    await expect(controlPanelLink).toHaveAttribute("href", EXPECTED_CONTROL_PANEL_URL);
  });

  test("standard profile does not show control panel entry when URL is configured", async ({
    page,
    context,
  }) => {
    await setUiProfileCookie(context, "standard");
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    await expect(page.getByRole("link", { name: CONTROL_PANEL_LABEL })).toHaveCount(0);
  });

  test("direct admin URL shows denial UX for non-admin role (403 messaging + recovery)", async ({
    page,
  }) => {
    await page.addInitScript(([roleKey]) => {
      window.localStorage.setItem(roleKey, "viewer");
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
    await page.goto(`${ADMIN_CONTRACT_BASE_URL}/`);
    await expect(page.getByText(/403 forbidden/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /access denied/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /return to legal search/i })).toBeVisible();
  });
});
