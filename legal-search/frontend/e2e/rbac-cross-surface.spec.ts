import type { BrowserContext, Page } from "@playwright/test";
import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

/** Must match `EVIDARA_UI_PROFILE_COOKIE` in `src/lib/control-plane-entry.ts`. */
const UI_PROFILE_COOKIE = "evidara-ui-profile";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const CONTROL_PANEL_LABEL = /control panel|kontrollbereich|panneau de contr[oô]le/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3101";
const EXPECTED_CONTROL_PANEL_URL =
  process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim() || "http://localhost:3100";
const USE_REAL_BACKEND = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";

/** Playwright `webServer`: admin dev server with non-admin role (`playwright.config.ts`). */
const ADMIN_CONTRACT_BASE_URL =
  process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3100";
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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function gotoWithRetry(page: Page, url: string, attempts = 3) {
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded" });
      return;
    } catch (error) {
      lastError = error;
      if (attempt === attempts) {
        throw error;
      }
      await page.waitForTimeout(750);
    }
  }

  throw lastError;
}
test.describe("@contract RBAC cross-surface (legal-search header + admin denial)", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("admin profile shows control panel entry when URL is configured", async ({ page }) => {
    await setUiProfileCookie(page.context(), "admin");
    await mockSearchApi(page);
    await gotoWithRetry(page, "/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    await expect(controlPanelLink).toBeVisible();
    const href = await controlPanelLink.getAttribute("href");
    expect(href).toBeTruthy();
    expect(new URL(href ?? "", LEGAL_SEARCH_BASE_URL).origin).toBe(
      new URL(EXPECTED_CONTROL_PANEL_URL).origin,
    );
    if (href && href !== EXPECTED_CONTROL_PANEL_URL) {
      expect(href).toMatch(new RegExp(`^${escapeRegExp(EXPECTED_CONTROL_PANEL_URL)}.*from=legal-search`));
    }
  });

  test("round-trips query, scope, and selected item through control panel and back", async ({
    page,
    context,
  }) => {
    await context.addInitScript(([roleKey, roleValue]) => {
      window.localStorage.setItem(roleKey, roleValue);
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY, "admin"]);

    const query = "Art 754 OR";
    // Localized (#648). The scope label handed to the control plane is
    // human-readable context and is now derived through the same translator the
    // workspace renders with, instead of being fabricated in English by the pure
    // reducer. The app's default locale is German — see `results.scope.resultsFor`
    // in `src/i18n/messages/de.json`.
    const scopeLabel = `Ergebnisse für „${query}“`;

    if (!USE_REAL_BACKEND) {
      await mockSearchApi(page);
    }
    await gotoWithRetry(page, `/?q=${encodeURIComponent(query)}`);

    if (USE_REAL_BACKEND) {
      await expect(page.locator("article").first()).toBeVisible();
    } else {
      await expect(page.getByText(`Result for ${query}`)).toBeVisible();
    }

    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);
    const selectedItem = new URL(page.url()).searchParams.get("item");
    expect(selectedItem).toBeTruthy();

    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    const href = await controlPanelLink.getAttribute("href");
    expect(href).toBeTruthy();

    const handoffUrl = new URL(href!, LEGAL_SEARCH_BASE_URL);
    expect(handoffUrl.searchParams.get("from")).toBe("legal-search");
    expect(handoffUrl.searchParams.get("ls_query")).toBe(query);
    expect(handoffUrl.searchParams.get("ls_item")).toBe(selectedItem);
    if (!USE_REAL_BACKEND) {
      expect(handoffUrl.searchParams.get("ls_scope")).toBe(scopeLabel);
    }

    await Promise.all([
      page.waitForURL((url) => url.toString().startsWith(EXPECTED_CONTROL_PANEL_URL)),
      controlPanelLink.click(),
    ]);

    await expect(page.getByText(/entered from legal search/i)).toBeVisible();
    await expect(page.getByText(`Search: ${query}`)).toBeVisible();
    if (!USE_REAL_BACKEND) {
      await expect(page.getByText(scopeLabel, { exact: true })).toBeVisible();
    }
    await expect(page.getByText(`Selected item: ${selectedItem}`, { exact: true })).toBeVisible();

    // Disambiguate: the admin chrome renders two "Return to active search"
    // links — the header link (exact label) and the sidebar footer link
    // (primary + secondary line).
    // We click the header link so the assertion remains scoped to the
    // original cross-surface return affordance.
    const returnLink = page.getByRole("link", {
      name: "Return to active search",
      exact: true,
    });
    await Promise.all([
      page.waitForURL((url) => {
        const parsed = new URL(url.toString());
        return (
          parsed.origin === new URL(LEGAL_SEARCH_BASE_URL).origin &&
          parsed.searchParams.get("q") === query &&
          parsed.searchParams.get("item") === selectedItem
        );
      }),
      returnLink.click(),
    ]);

    const returnedUrl = new URL(page.url());
    expect(returnedUrl.searchParams.get("q")).toBe(query);
    expect(returnedUrl.searchParams.get("item")).toBe(selectedItem);
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toHaveValue(query);
  });

  test("standard profile does not show control panel entry when URL is configured", async ({
    page,
    context,
  }) => {
    await setUiProfileCookie(context, "standard");
    await mockSearchApi(page);
    await gotoWithRetry(page, "/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();

    await expect(page.getByRole("link", { name: CONTROL_PANEL_LABEL })).toHaveCount(0);
  });

  test("direct admin URL shows denial UX for non-admin role (403 messaging + recovery)", async ({
    page,
  }) => {
    await page.addInitScript(([roleKey]) => {
      window.localStorage.setItem(roleKey, "viewer");
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
    await gotoWithRetry(page, `${ADMIN_CONTRACT_BASE_URL}/`);
    await expect(page.getByText(/403 forbidden/i)).toBeVisible();
    const accessDeniedHeading = page.getByRole("heading", { name: /access denied/i });
    if (await accessDeniedHeading.count()) {
      await expect(accessDeniedHeading).toBeVisible();
    } else {
      await expect(page.getByText(/access denied/i)).toBeVisible();
    }
    await expect(page.getByRole("link", { name: /return to legal search/i })).toBeVisible();
  });
});
