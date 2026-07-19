/**
 * Mobile workspace sheets (filters + detail).
 *
 * These assertions had rotted while the spec was reachable by no CI command
 * (#686): the UI now renders in German by default, and the mock fixtures no
 * longer produce the strings this file asserted ("Result for Bundesgericht",
 * "Mocked detail title" — the latter appears nowhere in helpers/mock-api.ts).
 * Text is matched the way e2e/smoke.spec.ts does it — locale-tolerant regexes
 * and values derived from the mock — so a locale default flip cannot silently
 * re-break the suite.
 */
import { expect, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

/** Matches the label in every shipped locale (en/de/fr). */
const FILTERS_LABEL = /^(filters|filter|filtres)$/i;

/** HomeClient.tsx seeds this query, and mock-api builds titles as `Result for ${query}`. */
const DEFAULT_QUERY = "Art. 754 OR Verantwortlichkeit";
const RESULT_TITLE = `Result for ${DEFAULT_QUERY}`;

/** buildDetail() in helpers/mock-api.ts. */
const DETAIL_TITLE = "BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats";

test.describe("Mobile workspace interactions", () => {
  test.use({ viewport: { width: 430, height: 932 } });

  test.beforeEach(async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    // The result list is server-driven; wait for it before touching the sheets
    // so a slow first render is not misreported as a missing control.
    await expect(page.getByRole("heading", { name: RESULT_TITLE })).toBeVisible();
  });

  test("opens and closes filters sheet", async ({ page }) => {
    // Two controls carry this label on mobile (the nav tab and the active-filter
    // summary button); the nav tab is the one that opens the sheet.
    await page.getByRole("button", { name: FILTERS_LABEL }).first().click();

    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(sheet).not.toBeVisible();
  });

  test("opens and closes detail sheet from result tap", async ({ page }) => {
    // A real anchor, not a button — #700 made it one so middle-click and
    // cmd/ctrl-click open a new tab (see ResultCard.tsx).
    await page.getByRole("link", { name: RESULT_TITLE }).click();
    await expect(page).toHaveURL(/item=decision-1/);

    await expect(page.getByRole("heading", { name: DETAIL_TITLE }).last()).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: DETAIL_TITLE }).last()).not.toBeVisible();
  });
});
