import { expect, test } from "@playwright/test";
import { mockAdminRunFlowApi } from "./helpers/mock-admin-api";
import { mockSearchApi } from "./helpers/mock-api";
import { forceExpandDetailPanel } from "./helpers/visual-stability";

const ADMIN_BASE_URL = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3100";
const ADMIN_LOCAL_STORAGE_ROLE_KEY = "evidara_user_role";
const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const DESKTOP_VIEWPORT = { width: 1600, height: 900 };
const MOBILE_VIEWPORT = { width: 430, height: 932 };

// Visual regressions run against a Next.js dev webServer that occasionally
// emits transient hot-reload SyntaxErrors between tests (the most common is
// `Unexpected end of JSON input` from an internal hot-update payload).
// These manifest as a Next.js error overlay covering the page on the *next*
// navigation, which then fails the `getByRole('banner')` assertion. Retry
// once so we don't gate the new W9 baselines on dev-server flake — visual
// drift will still surface because `--update-snapshots` only writes when
// the actual run produces a screenshot, and an in-flake retry that
// succeeds produces the same screenshot a clean run would.
test.describe.configure({ retries: 1 });

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
    //
    // The scope label is asserted in GERMAN on purpose. It used to read
    // `Results for "…"` — an untranslated English string in an otherwise fully
    // German UI (#648) — and this assertion pinned that bug as correct. It is
    // now derived through `next-intl` like its siblings.
    await expect(page.getByText("Ausgangssuche", { exact: true })).toHaveCount(1);
    await expect(page.getByText(/Ergebnisse für „Art\. 754/)).toHaveCount(1);

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
    await expect(page.getByText(/Ergebnisse für „Art\. 754/)).toHaveCount(1);

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
    // This is the only visual test that drives the *admin* dev server (port
    // 3100). Next.js `dev` compiles routes lazily on first request, and since
    // admin's `Pill` now pulls the shared `@evidara/ui` tree into the graph
    // (PR #503), that first cold compile can exceed the default 30s test
    // timeout — the `page.goto` below then times out on attempt 1 and the app
    // shell is still hydrating when attempt 2's 5s `toBeVisible` fires. Give
    // this test (and its first navigation) generous headroom so the one-time
    // cold compile completes deterministically; the frontend-only tests are
    // unaffected and keep the default budget.
    test.setTimeout(120_000);
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await page.addInitScript(([key]) => {
      window.localStorage.setItem(key, "admin");
    }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
    await page.setViewportSize({ width: 1600, height: 900 });

    await page.goto(`${ADMIN_BASE_URL}/#/runs-v2/run_01`, {
      waitUntil: "load",
      timeout: 90_000,
    });
    await expect(page.getByRole("heading", { name: /Decision support/ })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole("heading", { name: /Run run_01/ })).toBeVisible({
      timeout: 20_000,
    });
    // `RunDetailSectionsV2` renders collapsed accordion items below the
    // metadata grid. Wait for the `Provider Jobs` trigger so the capture
    // includes the full lifecycle stack (matches screenshot-pack framing).
    await expect(page.getByRole("button", { name: /Provider Jobs/ })).toBeVisible({
      timeout: 20_000,
    });

    await expect(page).toHaveScreenshot("admin-run-detail-v2.png", {
      fullPage: true,
    });
  });

  // ---------------------------------------------------------------------------
  // W9 — extended workspace surface coverage. Each test isolates one surface
  // (empty / error / detail / filter panel / multi-result) at one viewport
  // so a regression points at exactly one component. See
  // `docs/visual-snapshot-critique.md` §5 bug 7 for the original gap report.
  // ---------------------------------------------------------------------------

  test("empty search state (desktop) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { resultCount: 0 });
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto("/?q=zerohits");
    await expect(page.getByRole("banner")).toBeVisible();
    // ResultList renders the no-results empty state with the user's query
    // interpolated into the title — see `getEmptyStateCopy` in
    // `components/results/ResultList.tsx` and the `noResults` key in
    // `i18n/messages/de.json`.
    await expect(page.getByText(/Keine Ergebnisse für "zerohits"/)).toBeVisible();

    await expect(page).toHaveScreenshot("empty-state-desktop.png", {
      fullPage: true,
    });
  });

  // Mobile empty state diverges from desktop: `MobileWorkspace` renders
  // `ResultList` without the `query` prop, so `getEmptyStateCopy` falls
  // through to `startTitle`/`startHint` ("Suche starten") instead of
  // `noResults`. That's the actual product behaviour today, and the
  // baseline captures it — when mobile is wired through to honor `query`
  // (a separate UX ticket), this baseline will fail and need re-baselining
  // alongside the fix.
  test("empty search state (mobile) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { resultCount: 0 });
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto("/?q=zerohits");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByText("Suche starten")).toBeVisible();

    await expect(page).toHaveScreenshot("empty-state-mobile.png", {
      fullPage: true,
    });
  });

  // The error path is only reached via `executeSearch` (not the HomeClient
  // bootstrap, which silently degrades to an empty state on non-200). To
  // exercise it deterministically: serve a successful first response so the
  // page boots, then flip the failure flag and submit a fresh query through
  // the search input. The new `executeSearch` call throws and ResultList
  // renders the `<ErrorState>` branch (see `components/results/ResultList.tsx`).
  test("error search state (desktop) matches baseline", async ({ page }) => {
    let shouldFail = false;
    await mockSearchApi(page);
    await page.route("**/v1/search**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/v1/search" && shouldFail) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Internal Server Error" }),
        });
        return;
      }
      await route.fallback();
    });
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article").first()).toBeVisible();

    shouldFail = true;
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("trigger error");
    await searchInput.press("Enter");
    await expect(page.getByText("Suche fehlgeschlagen")).toBeVisible();

    await expect(page).toHaveScreenshot("error-state-desktop.png", {
      fullPage: true,
    });
  });

  test("error search state (mobile) matches baseline", async ({ page }) => {
    let shouldFail = false;
    await mockSearchApi(page);
    await page.route("**/v1/search**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/v1/search" && shouldFail) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Internal Server Error" }),
        });
        return;
      }
      await route.fallback();
    });
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article").first()).toBeVisible();

    shouldFail = true;
    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("trigger error");
    await searchInput.press("Enter");
    await expect(page.getByText("Suche fehlgeschlagen")).toBeVisible();

    await expect(page).toHaveScreenshot("error-state-mobile.png", {
      fullPage: true,
    });
  });

  // Detail panel (desktop) — open via click (URL-state opening leaves the
  // right panel at sub-`minSize` flex in headless Playwright; the same race
  // already required `forceExpandDetailPanel` in screenshot-pack). Click,
  // wait for the heading, then force the flex to a deterministic 40% before
  // capture so the baseline frames consistently.
  test("detail panel open (desktop) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { richDetail: true });
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);
    const detailPanel = page.locator('[data-testid="detail-panel"]');
    await expect(detailPanel).toBeVisible();
    await forceExpandDetailPanel(page);
    await expect(detailPanel.getByRole("heading", { name: /BGer 4A_123/ })).toBeVisible();

    await expect(page).toHaveScreenshot("detail-panel-desktop.png", {
      fullPage: true,
    });
  });

  // Detail sheet (mobile) — Radix `Sheet` portals into <body> and sets
  // `aria-hidden="true"` on the rest of the document while open, which
  // removes `<header role="banner">` from the accessibility tree. Skip the
  // banner assertion and validate the sheet directly. The sheet contains
  // *two* `BGer 4A_123` headings (Radix `SheetTitle` for the a11y label
  // and the visible H2 in the detail content); scope to the visible body
  // by waiting for a content-only marker (`Federal Supreme Court`) so the
  // capture frames the populated detail.
  test("detail sheet open (mobile) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { richDetail: true });
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto("/?item=decision-1");
    const sheetContent = page.locator('[data-slot="sheet-content"][data-state="open"]');
    await expect(sheetContent).toBeVisible();
    await expect(sheetContent.getByText("Federal Supreme Court").first()).toBeVisible();

    await expect(page).toHaveScreenshot("detail-sheet-mobile.png", {
      fullPage: true,
    });
  });

  // Filter panel with rich facets populated — desktop renders the filter
  // surface inline as the leftmost ResizablePanel; mobile renders it as a
  // left-side Radix `Sheet` (`FiltersSheet`) that the user opens from the
  // header. Capture the panel itself rather than the full page so the
  // baseline doesn't double-cover what `workspace-desktop` already proves.
  test("filter panel (desktop) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { richFacets: true });
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article").first()).toBeVisible();

    // First ResizablePanel is the filter rail — react-resizable-panels emits
    // `data-panel` per panel in JSX order; assert via a richFacets-only
    // option label (`Switzerland`) so a future panel reorder fails loudly.
    const filterPanel = page.locator("[data-panel]").first();
    await expect(filterPanel).toContainText("Switzerland");
    await expect(filterPanel).toContainText("Court level");

    await expect(filterPanel).toHaveScreenshot("filter-panel-desktop.png");
  });

  test("filter panel open (mobile) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { richFacets: true });
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    // The header has its own "Filter" trigger (`t("header.filters")`) AND
    // the ContextBar mobile collapse-toggle is also called "Filter" (with a
    // count badge from default jurisdiction/language constraints). Scope to
    // the banner so the locator is unambiguous; regex covers DE/FR copy.
    await page.getByRole("banner").getByRole("button", { name: /Filter|Filtres/ }).click();
    const sheetContent = page.locator('[data-slot="sheet-content"][data-state="open"]');
    await expect(sheetContent).toBeVisible();
    await expect(sheetContent.getByText("Switzerland")).toBeVisible();

    await expect(page).toHaveScreenshot("filter-panel-mobile.png", {
      fullPage: true,
    });
  });

  // Multi-result list — `workspace-desktop` proves shell + a single card.
  // This baseline proves the inter-card rhythm (border treatment, vertical
  // gap, scroll position at 5 stacked cards). Result count is fixed at 5 in
  // the mock so layout drift can't be masked by content drift.
  test("multi-result list (desktop) matches baseline", async ({ page }) => {
    await mockSearchApi(page, { resultCount: 5 });
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.locator("article")).toHaveCount(5);

    await expect(page).toHaveScreenshot("multi-result-desktop.png", {
      fullPage: true,
    });
  });
});
