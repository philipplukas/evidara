/**
 * Browser smoke for MVP acceptance (TAR-85). Pair with `evidara workflow mvp-acceptance`
 * for API-level evidence when filing release artifacts.
 */
import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER = /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const FILTERS_LABEL = /^(filters|filter|filtres)$/i;
const CONTROL_PANEL_LABEL = /control panel|kontrollbereich|panneau de contr[oô]le/i;
const EXPECTED_CONTROL_PANEL_URL =
  process.env.PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL?.trim() || "http://localhost:3100";
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3101";
const USE_REAL_BACKEND = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";
const REAL_BACKEND_API_URL = process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:3102";
const UI_PROFILE_COOKIE = "evidara-ui-profile";
const EMPTY_DETAIL_LABEL =
  /no result selected|select a result|kein ergebnis ausgewählt|aucun résultat sélectionné/i;

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
    } else {
      const probe = await page.request.get(
        `${REAL_BACKEND_API_URL}/v1/search?q=probe&page=1&page_size=1`,
        {
          failOnStatusCode: false,
          timeout: 5_000,
        },
      );
      if (!probe.ok()) {
        throw new Error(
          `Real backend mode requires a reachable search API at ${REAL_BACKEND_API_URL} (GET /v1/search).`,
        );
      }
    }
    await page.goto("/");
    if (USE_REAL_BACKEND) {
      const alert = page.getByRole("alert").first();
      if (await alert.isVisible().catch(() => false)) {
        const alertText = (await alert.textContent())?.trim() || "Unknown startup error";
        throw new Error(`Real backend smoke setup failed before assertions: ${alertText}`);
      }
    }
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();
  });

  test("@smoke renders app shell and default query", async ({ page }) => {
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await expect(searchInput).toHaveValue(/.+/);
    await expect(page.getByText(FILTERS_LABEL, { exact: true }).first()).toBeVisible();
    await expect(page.getByText(EMPTY_DETAIL_LABEL)).toBeAttached();
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
    await expect(page.getByText(EMPTY_DETAIL_LABEL)).toBeAttached();
  });

  test("@smoke exposes control panel entrypoint in header", async ({ page }) => {
    const controlPanelLink = page.getByRole("link", { name: CONTROL_PANEL_LABEL });
    await expect(controlPanelLink).toBeVisible();
    const href = await controlPanelLink.getAttribute("href");
    expect(href).toBeTruthy();
    expect(await controlPanelLink.getAttribute("target")).toBeNull();
    expect(href?.startsWith(EXPECTED_CONTROL_PANEL_URL)).toBe(true);
    if (href && href !== EXPECTED_CONTROL_PANEL_URL) {
      expect(href).toContain("from=legal-search");
    }
  });

  test("@smoke @real-api applies filters against live /v1/search", async ({ page }) => {
    test.skip(!USE_REAL_BACKEND, "real backend mode is opt-in via PLAYWRIGHT_USE_REAL_BACKEND=true");

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    const initialResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/v1/search?") && response.request().method() === "GET",
    );
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");

    const initialRequest = await initialResponsePromise;
    expect(initialRequest.ok()).toBe(true);
    const initialUrl = new URL(initialRequest.url());

    const firstCheckboxRow = page.locator('label:has(input[type="checkbox"])').first();
    await expect(firstCheckboxRow).toBeVisible();
    const filteredResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/v1/search?") && response.request().method() === "GET",
    );
    await firstCheckboxRow.click();

    const filteredRequest = await filteredResponsePromise;
    expect(filteredRequest.ok()).toBe(true);
    const filteredUrl = new URL(filteredRequest.url());

    expect(filteredUrl.search).not.toEqual(initialUrl.search);
    expect(filteredUrl.searchParams.toString().length).toBeGreaterThan(initialUrl.searchParams.toString().length);
  });
});
