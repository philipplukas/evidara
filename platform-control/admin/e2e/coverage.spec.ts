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
  total: 4,
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
      proposed_action: "enumerate_denominator",
      actor: "agent",
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
      proposed_action: "run_acceptance",
      actor: "agent",
    },
    {
      // A refused jurisdiction: the #964 case. Both reasons are true at once —
      // every run refused, so nothing acquired — and the server folds the actor
      // over every reason, so it is a person's however the queue is ordered.
      jurisdiction_id: "jur_ch_ag",
      name: "Kanton Aargau",
      slug: "jur-ch-ag",
      level: "cantonal",
      reasons: ["refusals_outstanding", "never_acquired"],
      expected: 210,
      denominator_tier: "published",
      acquired_distinct_urls: 0,
      processed_documents: 0,
      acquired_gap: 210,
      processed_gap: null,
      refused_runs: 3,
      quarantined_documents: 0,
      source_ids: ["src_ag"],
      proposed_action: "resolve_refusal",
      actor: "human",
    },
    {
      /*
       * A row whose `actor` does NOT follow from its reasons.
       *
       * Load-bearing: without it every human-owned row is also the refused row,
       * so counting the split from `reasons` gives the same answer as reading
       * `actor` and the assertion cannot tell the two apart. Measured — that
       * mutation passed until this row existed.
       *
       * Realistic, not contrived: `holdings_exceed_denominator` also folds to
       * human, and the server may add reasons this client has not learned. The
       * panel must believe the server either way.
       */
      jurisdiction_id: "jur_ch_be",
      name: "Kanton Bern",
      slug: "jur-ch-be",
      level: "cantonal",
      reasons: ["acquisition_gap"],
      expected: 400,
      denominator_tier: "published",
      acquired_distinct_urls: 120,
      processed_documents: 120,
      acquired_gap: 280,
      processed_gap: null,
      refused_runs: 0,
      quarantined_documents: 0,
      source_ids: ["src_be"],
      proposed_action: "run_acceptance",
      actor: "human",
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
    // The QUEUE's rows, every one with a source — not the LEDGER's fifty municipal
    // rows of zeroes, which is the whole point of #930. Tied to the fixture rather
    // than a literal so adding a queue row does not read as a regression here.
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(QUEUE.data.length);
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

/**
 * ADR-0056: the operator agent is visible in the panel.
 *
 * `agent_loop.py` has been deciding this per jurisdiction since #909, and nothing
 * rendered it — a control plane that could act, invisible in the product. These
 * assert the render, and that the panel never re-derives the decision (#964).
 */
test.describe("Coverage queue — the agent's work is legible, and the boundary holds", () => {
  test("each row states what to do next and who may do it", async ({ page }) => {
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    const refused = page.getByRole("row", { name: /Kanton Aargau/ });
    await expect(refused).toBeVisible({ timeout: 90_000 });
    await expect(refused).toContainText("Resolve the refusal");
    await expect(refused).toContainText("You");

    const gap = page.getByRole("row", { name: /Kanton Zürich/ });
    await expect(gap).toContainText("Run acceptance");
    await expect(gap).toContainText("Agent");
  });

  test("the refused row offers no way to retry it", async ({ page }) => {
    /*
     * ADR-0056 constraint 4, and the panel half of `agent_loop.py`'s
     * `test_no_refusal_is_ever_agent_actionable`. A refusal is a decision a person
     * made — a closed config key is how an operator stops traffic at a portal when
     * an authority complains about load. A retry affordance here is that override,
     * performed by the operator's own hand without being told what they are doing.
     */
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    const refused = page.getByRole("row", { name: /Kanton Aargau/ });
    await expect(refused).toBeVisible({ timeout: 90_000 });
    await expect(refused.getByRole("button", { name: /retry|re-?run|run now/i })).toHaveCount(0);
  });

  test("the actor split is counted from the server's answer, over the rows shown", async ({
    page,
  }) => {
    await mockCoverage(page);
    await page.goto("/#/acquisition-coverage");

    const split = page.getByTestId("queue-actor-split");
    await expect(split).toBeVisible({ timeout: 90_000 });
    // 3 rows: two agent-owned, one human-owned.
    await expect(split).toContainText("Of the 4 shown");
    await expect(split).toContainText("agent can work 2");
    await expect(split).toContainText("2 need you");
    // It must say the count is over what is displayed, not over the estate — the
    // server caps the queue, so a total claimed here would be about a population
    // this page has not seen (ADR-0042).
    await expect(split).toContainText("shown");
  });

  test("a server that calls a row human-owned is believed, whatever its reasons look like", async ({
    page,
  }) => {
    /*
     * The anti-re-derivation guard. If the panel ever computes `actor` from
     * `reasons` instead of reading the server's field, this row — whose reasons
     * alone read as ordinary acquisition work — flips to "Agent" and the test goes
     * red. That is #964 reproduced at its smallest.
     */
    // mockCoverage FIRST, then override: Playwright matches handlers in reverse
    // registration order, so a route registered before it would be shadowed.
    await mockCoverage(page);
    await page.route("**/v1/acquisition-coverage/queue*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...QUEUE,
          total: 1,
          data: [
            {
              ...QUEUE.data[1],
              jurisdiction_id: "jur_ch_probe",
              name: "Probe Jurisdiction",
              reasons: ["acquisition_gap"],
              proposed_action: "run_acceptance",
              actor: "human",
            },
          ],
        }),
      }),
    );
    await page.goto("/#/acquisition-coverage");

    const row = page.getByRole("row", { name: /Probe Jurisdiction/ });
    await expect(row).toBeVisible({ timeout: 90_000 });
    await expect(row).toContainText("You");
    await expect(row).not.toContainText("Agent");
  });
});
