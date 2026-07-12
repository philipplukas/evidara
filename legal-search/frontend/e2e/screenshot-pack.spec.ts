import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { type Page, expect, test } from "@playwright/test";
import { mockAdminRunFlowApi } from "./helpers/mock-admin-api";
import { mockSearchApi } from "./helpers/mock-api";

const SEARCH_PLACEHOLDER =
  /search article, case, commentary, citation|nach artikel, urteil, kommentar oder zitat|rechercher un article, un arrêt, un commentaire ou une citation/i;
const LEGAL_SEARCH_BASE_URL =
  process.env.PLAYWRIGHT_EXTERNAL_BASE_URL?.trim() || "http://localhost:3101";
const ADMIN_BASE_URL = process.env.PLAYWRIGHT_ADMIN_BASE_URL?.trim() || "http://localhost:3100";
const UI_PROFILE_COOKIE = "evidara-ui-profile";
const ADMIN_LOCAL_STORAGE_ROLE_KEY = "evidara_user_role";
const CANONICAL_VIEWPORT = { width: 1600, height: 900 };
const MOBILE_VIEWPORT = { width: 430, height: 932 };
const OUTPUT_DIR = "screenshot-pack";
const VIDEO_MODE = process.env.SCREENSHOT_PACK_VIDEO_MODE?.trim().toLowerCase() || "disabled";

async function hideDevToolWidgets(page: Page) {
  await page.addStyleTag({
    content: `
      /* Hide Next.js dev indicator and Tanstack Query devtools */
      [data-nextjs-dialog-overlay],
      [data-nextjs-toast],
      button[data-nextjs-dev-tools-button],
      .nextjs-portal,
      .tsqd-parent-container,
      [class*="ReactQueryDevtools"],
      [aria-label="Open Tanstack query devtools"],
      [aria-label="Open Next.js Dev Tools"] {
        display: none !important;
      }
    `,
  });
  await page.evaluate(() => {
    for (const tag of ["nextjs-portal", "next-dev-overlay"]) {
      for (const el of document.querySelectorAll(tag)) {
        el.remove();
      }
    }
    for (const el of document.querySelectorAll("body > [style]")) {
      const style = (el as HTMLElement).style;
      if (style.position === "fixed" && style.zIndex && Number(style.zIndex) > 9000) {
        el.remove();
      }
    }
    for (const el of document.querySelectorAll(".tsqd-parent-container")) {
      el.remove();
    }
  });
}

/**
 * Test-only insurance: react-resizable-panels can leave the detail panel at
 * sub-minSize width in headless Playwright after tab switches even though the
 * product fix (`resize(32)` in WorkspaceClient) works in real browsers. This
 * helper forces the panel to ~40% via direct flex manipulation; it's a no-op
 * when the panel is already wide.
 */
async function forceExpandDetailPanel(page: Page) {
  await page.evaluate(() => {
    const el = document.querySelector('[data-testid="detail-panel"]');
    const panelDiv = el?.parentElement?.parentElement as HTMLElement | null;
    if (!panelDiv?.hasAttribute("data-panel")) return;
    const currentFlex = Number.parseFloat(panelDiv.style.flex) || 0;
    if (currentFlex >= 20) return;
    panelDiv.style.flex = "40 1 0px";
    const group = panelDiv.parentElement;
    if (!group) return;
    for (const sib of Array.from(group.children)) {
      const s = sib as HTMLElement;
      if (s.hasAttribute("data-panel") && s !== panelDiv) {
        const current = Number.parseFloat(s.style.flex) || 50;
        s.style.flex = `${current * 0.5} 1 0px`;
      }
    }
  });
  await page.waitForTimeout(100);
}

async function saveScreenshot(page: Page, name: string, locator?: import("@playwright/test").Locator) {
  await hideDevToolWidgets(page);
  await mkdir(OUTPUT_DIR, { recursive: true });
  if (locator) {
    await locator.screenshot({
      path: join(OUTPUT_DIR, name),
      animations: "disabled",
    });
  } else {
    await page.screenshot({
      path: join(OUTPUT_DIR, name),
      fullPage: true,
      animations: "disabled",
    });
  }
}

async function saveOperatorJourneyEvents(page: Page) {
  const events = await page.evaluate(() => {
    const w = window as unknown as { __EVIDARA_OPERATOR_JOURNEY_EVENTS__?: unknown[] };
    return w.__EVIDARA_OPERATOR_JOURNEY_EVENTS__ ?? [];
  });
  await mkdir(OUTPUT_DIR, { recursive: true });
  await writeFile(join(OUTPUT_DIR, "operator-journey-events.json"), JSON.stringify(events, null, 2));
}

async function saveJourneyVideo(page: Page, name: string, enabled: boolean) {
  if (!enabled) {
    return;
  }
  const video = page.video();
  if (!video) {
    return;
  }
  await mkdir(OUTPUT_DIR, { recursive: true });
  await page.close();
  await video.saveAs(join(OUTPUT_DIR, name));
}

async function gotoWithRetry(page: Page, url: string, attempts = 3) {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await page.goto(url, { waitUntil: "load" });
      return;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        await page.waitForTimeout(1000 * attempt);
      }
    }
  }
  throw lastError;
}

async function setupAdmin(page: Page) {
  await page.addInitScript(([key]) => {
    window.localStorage.setItem(key, "admin");
  }, [ADMIN_LOCAL_STORAGE_ROLE_KEY]);
}

test.describe("Canonical screenshot evidence pack", () => {
  test.beforeAll(async () => {
    await rm(OUTPUT_DIR, { recursive: true, force: true });
  });

  test.beforeEach(async ({ page, context }) => {
    await page.setViewportSize(CANONICAL_VIEWPORT);
    await context.addCookies([
      {
        name: UI_PROFILE_COOKIE,
        value: "admin",
        url: new URL(LEGAL_SEARCH_BASE_URL).origin,
      },
    ]);
  });

  test("@screenshots captures legal-search and admin canonical surfaces", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await expect(page.locator("article").first()).toBeVisible();

    // Crop the header to its own artefact so the navigation/cross-surface
    // shot isn't byte-identical to the full results page (the user flagged
    // this in the Sprint 1 pack). `legal-search-result-list.png` remains the
    // full-page capture of the populated result list.
    await saveScreenshot(page, "cross-surface-header-navigation.png", page.getByRole("banner"));
    await saveScreenshot(page, "legal-search-result-list.png");

    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);
    await page.waitForTimeout(500);
    await forceExpandDetailPanel(page);

    await saveScreenshot(page, "legal-search-detail-panel.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/runs`);
    await expect(page.getByRole("button", { name: "Create Run" })).toBeVisible();
    await page.getByRole("button", { name: "Create Run" }).click();
    const createRunDialog = page.getByRole("dialog", { name: "Create Run" });
    await expect(createRunDialog).toBeVisible();
    await createRunDialog.getByRole("combobox", { name: /^Source$/ }).click();
    await page.getByRole("option", { name: "Swiss Federal Court" }).click();
    await createRunDialog.getByRole("combobox", { name: "Source version" }).click();
    await page.getByRole("option", { name: /2026.04.06/ }).click();
    await expect(page.getByText(/Preflight is blocking launch/i)).toBeVisible();
    await saveScreenshot(page, "admin-run-launch-preflight.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/runs/run_01/show`);
    await expect(page.getByRole("heading", { name: "Pipeline Health" })).toBeVisible();
    await expect(page.getByText("Operator Checklist")).toBeVisible();
    await expect(page.getByRole("link", { name: "Jump to DI processing" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open related evidence runbook" })).toBeVisible();
    await saveScreenshot(page, "admin-run-lifecycle-visibility.png");
    await saveOperatorJourneyEvents(page);
    await saveJourneyVideo(page, "cross-surface-journey.webm", VIDEO_MODE === "enabled");
  });

  test("@screenshots captures admin dashboard", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/`);
    await expect(page.getByText("Control Plane Overview")).toBeVisible();
    await expect(page.getByText("Recent Runs")).toBeVisible();
    await saveScreenshot(page, "admin-dashboard.png");
  });

  test("@screenshots captures admin source detail", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/sources/src_01/show`);
    await expect(page.getByRole("heading", { name: "Swiss Federal Court" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Source lifecycle" })).toBeVisible();
    await saveScreenshot(page, "admin-source-detail.png");
  });

  // ---------------------------------------------------------------------------
  // Sources list + detail capture. The Tailwind + ra-core ports graduated to
  // the canonical `/sources` routes (ADR-0026 P5 / #501, #509), so these hit
  // the same pages as the v1 captures above. The `-v2.png` output filenames
  // are retained as the documented UX-review artifacts (see
  // docs/runbooks/ux-aesthetic-review.md).
  // ---------------------------------------------------------------------------
  test("@screenshots captures admin sources list and detail", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/sources`);
    await expect(page.getByRole("heading", { name: /Sources/ })).toBeVisible();
    // Wait for reference data to resolve so the Jurisdiction / Authority
    // columns are populated before the capture.
    await expect(page.getByText("Swiss Federal Court")).toBeVisible();
    await saveScreenshot(page, "admin-sources-list-v2.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/sources/src_01/show`);
    await expect(page.getByRole("heading", { name: "Swiss Federal Court" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Source lifecycle" })).toBeVisible();
    await saveScreenshot(page, "admin-source-detail-v2.png");
  });

  test("@screenshots captures admin runs list and detail", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/runs`);
    await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
    // Wait for the first row to render so the preset count pills are
    // populated (otherwise the bar shows zeros for all statuses).
    await expect(page.locator("table tbody tr").first()).toBeVisible();
    await saveScreenshot(page, "admin-runs-list-v2.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/runs/run_01/show`);
    await expect(page.getByRole("heading", { name: /Decision support/ })).toBeVisible();
    // `Run run_01` heading renders at the top — wait for it so the status
    // pills and duration have resolved before capture.
    await expect(page.getByRole("heading", { name: /Run run_01/ })).toBeVisible();
    // P3 — `RunDetailSectionsV2` renders five collapsed accordion items
    // below the metadata grid. Wait for the `Provider Jobs` trigger so
    // the capture includes the full lifecycle stack.
    await expect(page.getByRole("button", { name: /Provider Jobs/ })).toBeVisible();
    await saveScreenshot(page, "admin-run-detail-v2.png");
  });

  test("@screenshots captures admin authority form v2 (create + edit)", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/authorities-v2/create`);
    await expect(page.getByRole("heading", { name: /Create authority/ })).toBeVisible();
    await expect(page.getByLabel("Name", { exact: true })).toBeVisible();
    await saveScreenshot(page, "admin-authority-create-v2.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/authorities-v2/auth_bger/edit`);
    await expect(page.getByRole("heading", { name: /Edit Bundesgericht/ })).toBeVisible();
    // Wait for useEditController to hydrate the record so the Name field
    // has its existing value before we capture.
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Bundesgericht");
    await saveScreenshot(page, "admin-authority-edit-v2.png");
  });

  test("@screenshots captures admin source create form", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/sources/create`);
    await expect(page.getByRole("heading", { name: /Create source/ })).toBeVisible();
    // Wait for useGetList("jurisdictions") to hydrate so the Select has
    // at least one real option before the capture. The jurisdiction
    // helperText is static, so assert via the combobox trigger — radix
    // renders the trigger with role="combobox" and the accessible name
    // from the label via `htmlFor`.
    const jurisdictionTrigger = page.getByRole("combobox", { name: "Jurisdiction" });
    await expect(jurisdictionTrigger).toBeVisible();
    await jurisdictionTrigger.click();
    await expect(page.getByRole("option", { name: /Switzerland/ })).toBeVisible();
    // Dismiss the open listbox so the captured frame shows the closed
    // trigger, matching the other form screenshots in the pack.
    await page.keyboard.press("Escape");
    await saveScreenshot(page, "admin-source-create-v2.png");
  });

  test("@screenshots captures admin jurisdiction form v2 (create + edit)", async ({ page }) => {
    await mockSearchApi(page);
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/jurisdictions-v2/create`);
    await expect(page.getByRole("heading", { name: /Create jurisdiction/ })).toBeVisible();
    await expect(page.getByLabel("Name", { exact: true })).toBeVisible();
    await saveScreenshot(page, "admin-jurisdiction-create-v2.png");

    await gotoWithRetry(page, `${ADMIN_BASE_URL}/#/jurisdictions-v2/jur_ch/edit`);
    await expect(page.getByRole("heading", { name: /Edit Switzerland/ })).toBeVisible();
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Switzerland");
    await saveScreenshot(page, "admin-jurisdiction-edit-v2.png");
  });

  test("@screenshots captures filter panel with data", async ({ page }) => {
    await mockSearchApi(page, { richFacets: true });
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await expect(page.locator("article").first()).toBeVisible();
    await saveScreenshot(page, "legal-search-filter-panel-populated.png");
  });

  test("@screenshots captures detail panel secondary tabs", async ({ page }) => {
    await mockSearchApi(page, { richFacets: true, richDetail: true });
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);

    const detailPanel = page.locator('[data-testid="detail-panel"]');
    await page.waitForTimeout(1000);
    await forceExpandDetailPanel(page);
    await saveScreenshot(page, "detail-tab-details.png", detailPanel);

    const relatedTab = detailPanel.getByRole("tab", { name: /Related/i });
    await relatedTab.click();
    await forceExpandDetailPanel(page);
    await expect(page.getByText("Applied norms")).toBeVisible();
    await saveScreenshot(page, "detail-tab-related.png", detailPanel);

    const referencesTab = detailPanel.getByRole("tab", { name: /References/i });
    await referencesTab.click();
    await forceExpandDetailPanel(page);
    await expect(page.getByText("Cited by")).toBeVisible();
    await saveScreenshot(page, "detail-tab-references.png", detailPanel);
  });

  test("@screenshots captures mobile responsive layout", async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await mockSearchApi(page, { richFacets: true });
    await mockAdminRunFlowApi(page);
    await setupAdmin(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();

    // Mobile landing (pre-query) — captures the mobile masthead + empty
    // state before the user types a search term. Distinct from the
    // populated `mobile-result-list.png` below.
    await saveScreenshot(page, "mobile-search-home.png");

    const searchInput = page.getByPlaceholder(SEARCH_PLACEHOLDER);
    await searchInput.fill("Art. 754");
    await searchInput.press("Enter");
    await expect(page.locator("article").first()).toBeVisible();

    await saveScreenshot(page, "mobile-result-list.png");

    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=/);
    await saveScreenshot(page, "mobile-detail-sheet.png");
  });
});
