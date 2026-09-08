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
import { expect, type Page, test } from "@playwright/test";

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
  version_label: "v1",
  status: "approved",
  extractor_profile_id: "xp_lexfind_law",
  acquisition_spec: { provider: "lexfind", cantons: ["zh"], enabled: true },
  created_at: "2026-09-05T11:39:04Z",
  updated_at: "2026-09-05T11:40:00Z",
};

async function mockApi(page: Page) {
  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });

  await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) =>
    route.fulfill(json({ data: [{ jurisdiction_id: "jur_ch_zh", name: "Zürich" }], total: 1 })),
  );
  await page.route("**/api/platform-control/v1/reference-data/authorities*", (route) =>
    route.fulfill(json({ data: [{ authority_id: "auth_zh_sk", name: "Staatskanzlei ZH" }], total: 1 })),
  );
  await page.route("**/api/platform-control/v1/runs/readiness*", (route) =>
    route.fulfill(json({ data: [], total: 0 })),
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
    await page.goto(`/#/sources/${SOURCE_ID}/show`);

    const header = page.getByRole("columnheader", { name: "Actions" });
    await expect(header).toBeVisible();
    // Computed style, not a class name — this is the assertion jsdom cannot make.
    await expect(header).toHaveCSS("position", "sticky");

    // Approve and Reject are the ADR-0033 gate. If any single one of these is
    // outside the viewport the operator cannot act without discovering a scroll
    // they were never told about, which is the whole finding.
    for (const name of ["Edit", "Config", "Preview run", "Production run", "Approve", "Reject"]) {
      await expect(page.getByRole("button", { name, exact: true })).toBeInViewport();
    }
  });

  test("the pinned cell keeps an opaque ground, so scrolled columns do not show through", async ({
    page,
  }) => {
    await mockApi(page);
    await page.setViewportSize({ width: 1280, height: 950 });
    await page.goto(`/#/sources/${SOURCE_ID}/show`);

    const cell = page.getByRole("button", { name: "Approve", exact: true }).locator("xpath=ancestor::td[1]");
    await expect(cell).toHaveCSS("position", "sticky");
    // A transparent pinned cell is worse than no pin: the columns it floats
    // over render straight through the buttons.
    const background = await cell.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(background).not.toBe("rgba(0, 0, 0, 0)");
    expect(background).not.toBe("transparent");
  });
});
