/**
 * Coverage — the first Playwright coverage this view has ever had (#930, #929).
 *
 * It opened on page 1 of 44: fifty municipal rows reading `expected —,
 * acquired 0`, while its own summary header said four of 2,169 jurisdictions
 * had any acquisition — and offered no way to reach them. The screen knew the
 * answer and made it unreachable.
 *
 * Every request is mocked with `page.route`; no backend.
 */
import { expect, type Page, test } from "@playwright/test";

const LEDGER = {
  basis: "platform_control_runs",
  as_of: "2026-09-08T09:00:00Z",
  summary: {
    jurisdictions_total: 2169,
    jurisdictions_with_any_acquired: 4,
    jurisdictions_with_any_processed: 4,
    jurisdictions_with_published_denominator: 1,
    jurisdictions_with_registry_denominator: 0,
    reconciliations_unattributed: 0,
    processed_documents_unattributable: 0,
    quarantined_events_unattributable: 0,
    reconciliations_recorded_since: null,
    unmeasured_stages: ["indexed"],
  },
  data: [],
  total: 2169,
  limit: 1,
  offset: 0,
};

const QUEUE = {
  basis: "platform_control_runs",
  as_of: "2026-09-08T09:00:00Z",
  ordering: "reason_class_then_name",
  unqueued_unmeasurable: 0,
  jurisdictions_without_a_source: 2164,
  total: 2,
  limit: 50,
  data: [
    {
      jurisdiction_id: "jur_ch_bs",
      name: "Kanton Basel-Stadt",
      slug: "jur-ch-bs",
      level: "cantonal",
      reasons: ["no_denominator"],
      expected: null,
      denominator_tier: "none",
      acquired_distinct_urls: 5,
      processed_documents: 5,
      acquired_gap: null,
      processed_gap: null,
      refused_runs: 0,
      quarantined_documents: 0,
      source_ids: ["src_bs"],
    },
    {
      jurisdiction_id: "jur_ch_zh",
      name: "Kanton Zürich",
      slug: "jur-ch-zh",
      level: "cantonal",
      reasons: ["acquisition_gap", "processing_gap"],
      expected: 1378,
      denominator_tier: "published",
      acquired_distinct_urls: 944,
      processed_documents: 890,
      acquired_gap: 434,
      processed_gap: 488,
      refused_runs: 0,
      quarantined_documents: 0,
      source_ids: ["src_zh_a", "src_zh_b"],
    },
  ],
};

async function mockCoverage(page: Page) {
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );
  await page.route("**/v1/acquisition-coverage/queue*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUEUE) }),
  );
  await page.route("**/v1/acquisition-coverage?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(LEDGER) }),
  );
  await page.addInitScript(() => {
    window.localStorage.setItem("evidara_user_role", "admin");
  });
}

test.describe("Coverage — the screen answers the question it is for (#930)", () => {
  test("opens on the jurisdictions that need work, not on empty communes", async ({ page }) => {
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    await expect(page.getByRole("button", { name: /Needs work/ })).toBeVisible();
    // Two rows, both with a source — not fifty municipal rows of zeroes.
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(page.getByText("Kanton Zürich")).toBeVisible();
  });

  test("shows every reason a row has, not a chosen one", async ({ page }) => {
    // The server deliberately emits no ranking and no score (ADR-0042). Picking
    // one reason here would be the client inventing what the API refused to.
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    const zurich = page.getByRole("row", { name: /Kanton Zürich/ });
    await expect(zurich.getByText("Acquisition gap")).toBeVisible();
    await expect(zurich.getByText("Processing gap")).toBeVisible();
  });

  test("states the sourceless jurisdictions as a count rather than hiding them", async ({
    page,
  }) => {
    // 2,164 rows would bury the two real ones; silence would be worse. The
    // count is the honest middle.
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    await expect(page.getByText(/2164 jurisdictions have no source at all/)).toBeVisible();
  });

  test("keeps the em dash for an absent denominator, and never a zero", async ({ page }) => {
    // The rule this view already carried and must not lose: a column of zeros
    // reads as "these publish no law" rather than "nobody told us how much".
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    const basel = page.getByRole("row", { name: /Kanton Basel-Stadt/ });
    await expect(basel.getByText("—")).toBeVisible();
    // Zürich has a real denominator, so it shows the number.
    await expect(page.getByRole("row", { name: /Kanton Zürich/ }).getByText("1378")).toBeVisible();
  });

  test("the full ledger is still reachable", async ({ page }) => {
    // The work queue is a VIEW of the ledger, not a replacement — looking one
    // jurisdiction up is still a real question.
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    await page.getByRole("button", { name: "All jurisdictions" }).click();
    await expect(page.getByRole("button", { name: "Municipal" })).toBeVisible();
  });
});
