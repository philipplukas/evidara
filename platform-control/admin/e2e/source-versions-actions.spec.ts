/**
 * The source-versions table's Actions column must survive the fold.
 *
 * This is the M16 finding (#873) re-created outside the primitive that fixed
 * it. `DataTable` grew `stickyRight` precisely so an operator's levers cannot
 * scroll away, but `SourceVersionsSection` hand-rolls its own
 * `<div class="overflow-x-auto"><table>` — because it renders expandable diff
 * and spec sub-rows `DataTable` has no notion of — and so inherited none of it.
 *
 * Measured on the running panel at 1280x950 before the fix:
 *
 *   scroller   left=361  clientWidth=844  scrollWidth=972  → visible to x=1207
 *   every button                                             left=1227
 *
 * Twenty pixels past the edge. Edit, Config, Preview run, Production run and
 * the ADR-0033 Approve/Reject gate were all invisible, with no fade, no caption
 * hint and no scrollbar cue — so the table read as if the version had no
 * actions at all.
 *
 * No Vitest layer can see this: jsdom has no layout engine, so the column's
 * geometry does not exist there. This spec is the layer that can.
 */

import type { Page } from "@playwright/test";
import { expect, test } from "./support/test";

const SOURCE_ID = "src_e2e_versions";

const SOURCE = {
  source_id: SOURCE_ID,
  name: "ZH cantonal LexFind full-canton acceptance",
  description: null,
  jurisdiction_id: "jur_ch_zh",
  authority_id: "auth_zh_sk",
  source_type: "api",
  document_family: "law",
  status: "active",
  created_at: "2026-09-05T11:39:04Z",
  updated_at: "2026-09-05T11:39:04Z",
};

/**
 * Approved, so the row renders the widest action set — Edit, Config, both run
 * buttons, and the Approve/Reject gate. A narrower row would not reproduce the
 * overflow the finding is about.
 */
const VERSION = {
  id: "sv_e2e_1",
  source_version_id: "sv_e2e_1",
  source_id: SOURCE_ID,
  // A realistic label and spec, copied in shape from a live version. This is
  // load-bearing: a thin fixture does not make the table overflow at 1280, and
  // the test would then pass by having nothing to measure. The `overflows`
  // assertion below fails loudly if that ever becomes true again.
  version_label: "ch-zh-lexfind-full-canton-20260905T113904Z",
  status: "approved",
  extractor_profile_id: "exp_legislation_v1",
  acquisition_spec: {
    tenant_id: "tenant_public",
    corpus_id: "corpus_public_ch_canton_zh_legislation",
    scope_type: "global_public",
    source_origin_kind: "official_primary",
    trust_tier: "authoritative",
    language_codes: ["de"],
    document_type_hint: "legislation",
    request_timeout_seconds: 20.0,
    max_content_bytes: 2000000,
    provider: "lexfind_api",
    enumeration: "systematic_digit_union",
    entity_ids: [26],
    language: "de",
    results_per_page: 100,
    max_pages: 40,
    min_pdf_bytes: 2000,
  },
  created_at: "2026-09-05T11:39:04Z",
  updated_at: "2026-09-05T11:40:00Z",
};

/**
 * The panel is served by a dev server this run starts cold, so the first
 * navigation waits on a Turbopack compile that outruns Playwright's default 5s
 * assertion timeout. Waiting on the shell explicitly keeps a slow compile from
 * reading as a missing column.
 */
async function gotoSourceDetail(page: Page) {
  await page.goto(`/#/sources/${SOURCE_ID}/show`);
  await expect(page.getByTestId("source-versions-section")).toBeVisible({ timeout: 90_000 });
}

async function mockApi(page: Page) {
  /*
   * The operator role, set in localStorage BEFORE the app boots.
   *
   * Not optional, and the reason it was missed is worth recording: a local dev
   * server reads `NEXT_PUBLIC_USER_ROLE` from `.env.local` and bakes it in at
   * BUILD time, so these specs passed on a workstation while setting no role at
   * all. CI builds without that file, the role falls back to localStorage, and
   * every protected view renders empty — which surfaces as
   * "element(s) not found", indistinguishable from the column being missing.
   */
  await page.addInitScript(() => {
    window.localStorage.setItem("evidara_user_role", "admin");
  });

  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });

  await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) =>
    route.fulfill(json({ data: [{ jurisdiction_id: "jur_ch_zh", name: "Zürich" }], total: 1 })),
  );
  await page.route("**/api/platform-control/v1/reference-data/authorities*", (route) =>
    route.fulfill(
      json({ data: [{ authority_id: "auth_zh_sk", name: "Staatskanzlei ZH" }], total: 1 }),
    ),
  );
  // Readiness is NOT a list envelope — it returns `{ready, checks:[...]}` and the
  // panel filters `checks`. Mocking it as `{data,total}` crashed the whole route
  // with "Cannot read properties of undefined (reading 'filter')", which renders
  // as react-admin's generic error page and looks exactly like a missing column.
  await page.route("**/api/platform-control/v1/runs/readiness*", (route) =>
    route.fulfill(
      json({
        source_id: SOURCE_ID,
        source_version_id: VERSION.source_version_id,
        mode: "production",
        ready: true,
        checks: [{ code: "source_exists", ok: true, detail: "Source exists." }],
      }),
    ),
  );
  await page.route(`**/api/platform-control/v1/sources/${SOURCE_ID}/versions*`, (route) =>
    route.fulfill(json({ data: [VERSION], total: 1 })),
  );
  await page.route(`**/api/platform-control/v1/sources/${SOURCE_ID}`, (route) =>
    route.fulfill(json(SOURCE)),
  );
}

test.describe("Source versions — the operator's levers survive the fold", () => {
  test("the Actions column is pinned and every action is in the viewport at 1280", async ({
    page,
  }) => {
    await mockApi(page);
    // The width the finding was measured at. At 1440 this table does not
    // overflow at all (scrollWidth == clientWidth == 1004), so a test run only
    // at 1440 would have passed over the defect.
    await page.setViewportSize({ width: 1280, height: 950 });
    await gotoSourceDetail(page);

    const header = page.getByRole("columnheader", { name: "Actions" });
    await expect(header).toBeVisible();
    // Computed style, not a class name — this is the assertion jsdom cannot make.
    await expect(header).toHaveCSS("position", "sticky");

    // Approve and Reject are the ADR-0033 gate. The defect is HORIZONTAL: the
    // buttons sat past the right edge of a scroller nothing said was scrollable.
    //
    // Measured through `page.evaluate`, NOT through Playwright locators.
    // `locator.boundingBox()` scrolls the element into view before it measures,
    // so it reveals the very clipping it is being asked about — an earlier
    // version of this test used it and passed with the pin removed. Reading
    // `getBoundingClientRect()` in the page, with the scroller left where it
    // loads, is the only way to see what the operator sees.
    const geometry = await page.evaluate(() => {
      const table = [...document.querySelectorAll("table")].find((t) =>
        /Actions/.test(t.textContent ?? ""),
      );
      if (!table) return null;
      const scroller = table.parentElement as HTMLElement;
      const scrollerRect = scroller.getBoundingClientRect();
      const actionCell = table.querySelector("tbody tr td:last-child") as HTMLElement | null;
      const buttons = [...(actionCell?.querySelectorAll("button") ?? [])].map((b) => ({
        label: (b.textContent ?? "").trim(),
        right: Math.round(b.getBoundingClientRect().right),
      }));
      return {
        scrollLeft: scroller.scrollLeft,
        overflows: scroller.scrollWidth > scroller.clientWidth + 1,
        // Where the operator can actually see up to.
        visibleRight: Math.min(Math.round(scrollerRect.right), window.innerWidth),
        buttons,
      };
    });

    expect(geometry, "the versions table did not render").not.toBeNull();
    // Guard against the guard: if the table stopped overflowing at 1280 this
    // assertion would be vacuously true, so fail loudly instead of abstaining.
    expect(geometry!.overflows, "table no longer overflows at 1280 — retune this test").toBe(true);
    expect(geometry!.scrollLeft, "test scrolled the table before measuring").toBe(0);
    expect(geometry!.buttons.length).toBeGreaterThanOrEqual(6);

    for (const button of geometry!.buttons) {
      expect(
        button.right,
        `"${button.label}" is cut off at x=${button.right}, past the visible edge x=${geometry!.visibleRight}`,
      ).toBeLessThanOrEqual(geometry!.visibleRight);
    }
  });

  test("the pinned cell keeps an opaque ground, so scrolled columns do not show through", async ({
    page,
  }) => {
    await mockApi(page);
    await page.setViewportSize({ width: 1280, height: 950 });
    await gotoSourceDetail(page);

    const cell = page
      .getByRole("button", { name: "Approve", exact: true })
      .locator("xpath=ancestor::td[1]");
    await expect(cell).toHaveCSS("position", "sticky");
    // A transparent pinned cell is worse than no pin: the columns it floats
    // over render straight through the buttons.
    const background = await cell.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(background).not.toBe("rgba(0, 0, 0, 0)");
    expect(background).not.toBe("transparent");
  });
});
