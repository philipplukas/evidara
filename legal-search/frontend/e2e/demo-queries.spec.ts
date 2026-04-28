/**
 * Demo-query regression smoke. Pins the queries the demo presenter will
 * actually type, so a silent ranking shift between today and demo day
 * fails CI before the demo, not on stage.
 *
 * Pairs with docs/demo/script.md (narrative + final query table) and
 * docs/demo/detail-view-audit.md (per-document trust-signal checklist).
 *
 * Real-backend only. Mocking defeats the purpose — we want to know if
 * the actual prod ranker still puts the right doc at top-1.
 *
 * Run against prod:
 *   PLAYWRIGHT_USE_REAL_BACKEND=true \
 *     NEXT_PUBLIC_API_URL=https://<prod-legal-search-api> \
 *     PLAYWRIGHT_EXTERNAL_BASE_URL=https://<prod-legal-search-frontend> \
 *     npx playwright test e2e/demo-queries.spec.ts
 */
import { expect, test } from "@playwright/test";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3101";
const REAL_BACKEND_API_URL =
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:3102";
const USE_REAL_BACKEND = process.env.PLAYWRIGHT_USE_REAL_BACKEND === "true";
const UI_PROFILE_COOKIE = "evidara-ui-profile";

interface DemoQuery {
  /** Short label for the test name. */
  name: string;
  /** Exact text the presenter will type. */
  query: string;
  /**
   * Expected top-1 document id, e.g. `doc_67b9202dsxm52sa36dsfvcm6bt` (OR).
   * Pin this once the presenter has chosen the rehearsed list.
   * Leave undefined for backup queries that are not yet committed; the
   * test will still assert at least one result returns.
   */
  expectedTopDocId?: string;
  /**
   * Substring that must appear in the top-1 snippet (case-insensitive).
   * Use a token the demo audience will visibly recognize.
   */
  snippetContains?: string;
  /** Skip the query for now without removing the placeholder row. */
  skip?: boolean;
}

/**
 * The rehearsed query table. Mirror this with docs/demo/script.md before
 * T-7. Items marked `skip: true` are placeholders for queries the
 * presenter has not yet committed to.
 */
const DEMO_QUERIES: DemoQuery[] = [
  {
    name: "hero — Art. 754 OR Verantwortlichkeit",
    query: "Art. 754 OR Verantwortlichkeit",
    // Code of Obligations (OR) — board liability article.
    expectedTopDocId: "doc_67b9202dsxm52sa36dsfvcm6bt",
    snippetContains: "Verantwortlichkeit",
  },
  {
    name: "backup 1 — TBD",
    query: "TBD",
    skip: true,
  },
  {
    name: "backup 2 — TBD",
    query: "TBD",
    skip: true,
  },
  {
    name: "backup 3 — TBD",
    query: "TBD",
    skip: true,
  },
];

test.describe("@demo demo-query regression smoke", () => {
  test.beforeEach(async ({ page, context }) => {
    test.skip(
      !USE_REAL_BACKEND,
      "demo-query smoke is real-backend only; set PLAYWRIGHT_USE_REAL_BACKEND=true",
    );

    await context.addCookies([
      {
        name: UI_PROFILE_COOKIE,
        value: "admin",
        url: new URL(LEGAL_SEARCH_BASE_URL).origin,
      },
    ]);

    const probe = await page.request.get(
      `${REAL_BACKEND_API_URL}/v1/search?q=probe&page=1&page_size=1`,
      { failOnStatusCode: false, timeout: 5_000 },
    );
    if (!probe.ok()) {
      throw new Error(
        `Real backend mode requires a reachable search API at ${REAL_BACKEND_API_URL} (GET /v1/search).`,
      );
    }

    await page.goto("/");
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();
  });

  for (const q of DEMO_QUERIES) {
    const title = `@demo ${q.name}`;

    test(title, async ({ page }) => {
      test.skip(q.skip === true, `query not yet committed: ${q.name}`);

      const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
      const responsePromise = page.waitForResponse(
        (response) =>
          response.url().includes("/v1/search?") && response.request().method() === "GET",
      );

      await searchInput.fill(q.query);
      await searchInput.press("Enter");

      const response = await responsePromise;
      expect(response.ok(), `search request failed for ${q.query}`).toBe(true);

      const firstResult = page.locator("article").first();
      await expect(
        firstResult,
        `query "${q.query}" returned no results`,
      ).toBeVisible();

      if (q.expectedTopDocId) {
        // The result card carries the doc id; assert by clicking and
        // checking the URL, which mirrors how the smoke spec validates
        // selection.
        await firstResult.click();
        await expect(
          page,
          `query "${q.query}" did not land on expected top-1 ${q.expectedTopDocId}`,
        ).toHaveURL(new RegExp(`item=${q.expectedTopDocId}\\b`));
      }

      if (q.snippetContains) {
        const text = (await firstResult.innerText()).toLowerCase();
        expect(
          text,
          `top-1 snippet for "${q.query}" missing expected token "${q.snippetContains}"`,
        ).toContain(q.snippetContains.toLowerCase());
      }
    });
  }
});
