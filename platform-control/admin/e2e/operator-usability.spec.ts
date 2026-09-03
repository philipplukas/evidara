/**
 * M16 regressions — the ones only the *running* app can show.
 *
 * Every finding here was found by driving the built panel, not by reading it,
 * and each is invisible to Vitest for the same reason: jsdom has no layout
 * engine (so it cannot see a clipped column), applies no stylesheet (so it
 * cannot see a UA bevel or a missing dark palette), and mounts no router (so it
 * cannot see that nothing links to the dashboard). This spec is the layer that
 * can.
 *
 * It lives in its own file rather than being folded into the existing specs so
 * the M16 evidence is reviewable as one thing.
 */
import { expect, type Page, test } from "@playwright/test";

const COMPLETED_RUN = {
  run_id: "run_done_1",
  source_id: "src_1",
  source_version_id: "sv_1",
  source_name: "CH Fedlex Tierschutz acceptance",
  version_label: "v1",
  mode: "production",
  status: "completed",
  started_at: "2026-04-14T09:00:00Z",
  completed_at: "2026-04-14T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-14T08:55:00Z",
  updated_at: "2026-04-14T09:30:00Z",
};

const RUNNING_RUN = {
  ...COMPLETED_RUN,
  run_id: "run_running_1",
  status: "running",
  completed_at: null,
  created_at: "2026-04-15T09:05:00Z",
  updated_at: "2026-04-15T09:20:00Z",
};

const FAILED_RUN = {
  ...COMPLETED_RUN,
  run_id: "run_failed_1",
  status: "failed",
  mode: "acceptance",
  completed_at: null,
  failure_reason:
    "Demo fixture: provider returned HTTP 503 for 2 of 2 captured resources, after 3 retries against the upstream host.",
  created_at: "2026-04-15T09:40:00Z",
  updated_at: "2026-04-15T09:41:00Z",
};

/** Queued long enough ago that the staleness cue must fire. */
const STALE_PENDING_RUN = {
  ...COMPLETED_RUN,
  run_id: "run_pending_stale",
  status: "pending",
  started_at: null,
  completed_at: null,
  created_at: "2020-01-01T00:00:00Z",
  updated_at: "2020-01-01T00:00:00Z",
};

async function mockApi(page: Page, runs: object[]) {
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );
  await page.route("**/api/platform-control/v1/runs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: runs, total: runs.length, limit: 25, offset: 0 }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("evidara_user_role", "admin");
  });
});

test.describe("Run queue — the attention chip tells the truth (M16 #2)", () => {
  test("an all-completed queue reports no attention run, matching the dashboard", async ({
    page,
  }) => {
    // The defect: the selector ended in a `runs[0]` fallback, so five completed
    // runs produced an amber "Open attention run · CH Fedlex Tierschutz
    // acceptance" chip pointing at a *completed* run — while the dashboard, on
    // the same data, said "nothing needing attention" and disabled its button.
    await mockApi(page, [COMPLETED_RUN]);
    await page.goto("/#/runs");

    await expect(page.getByText("run_done_1")).toBeVisible();
    await expect(page.getByRole("button", { name: /Open attention run/ })).toHaveCount(0);
    await expect(page.getByTestId("run-queue-no-attention")).toContainText(
      "No run is failing, pending, or running",
    );
  });

  test("an actionable run still gets the chip", async ({ page }) => {
    await mockApi(page, [RUNNING_RUN, COMPLETED_RUN]);
    await page.goto("/#/runs");

    await expect(page.getByRole("button", { name: /Open attention run/ })).toBeVisible();
    await expect(page.getByTestId("run-queue-no-attention")).toHaveCount(0);
  });
});

test.describe("Run queue — the operator's levers survive the fold (M16 #1)", () => {
  test("the Actions column is pinned and the table says it scrolls", async ({ page }) => {
    await mockApi(page, [RUNNING_RUN, COMPLETED_RUN]);
    // The reported viewport: a standard laptop, where scrollWidth 1160 exceeded
    // clientWidth 1054 and ACTIONS — cancel and retry, the only levers on a
    // live run — sat past the right edge with no cue at all.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/#/runs");

    const header = page.getByRole("columnheader", { name: "Actions" });
    await expect(header).toBeVisible();
    // Computed style, not a class name: this is the assertion jsdom cannot make.
    await expect(header).toHaveCSS("position", "sticky");

    const cancel = page.getByRole("row", { name: /run_running_1/ }).getByRole("button", {
      name: "Cancel",
    });
    await expect(cancel).toBeInViewport();
  });

  test("at 390px the cancel action is still reachable", async ({ page }) => {
    // At this width the table used to lose everything but RUN and a sliver of
    // SOURCE — a mobile run queue of opaque ULIDs with no controls.
    await mockApi(page, [RUNNING_RUN]);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/runs");

    // Scoped to the row: "Cancelled 0" is one of the preset chips above the
    // table, and a bare "Cancel" name matches it too.
    const cancel = page
      .getByRole("row", { name: /run_running_1/ })
      .getByRole("button", { name: "Cancel", exact: true });
    await expect(cancel).toBeVisible();

    // Vertical scroll is expected on a 390px-tall page and is not what this
    // test is about; horizontal reach is. With the table scrolled fully left —
    // the position it loads in, and the one where ACTIONS used to be entirely
    // off-screen — the control must sit inside the viewport's width.
    await cancel.scrollIntoViewIfNeeded();
    const box = await cancel.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(391);
  });

  test("a sortable header is not a raw browser button", async ({ page }) => {
    // Measured on the live app: `border: 2px outset rgb(0,0,0)` — the UA
    // default, because globals.css skips Tailwind's preflight. It reads as a
    // stuck focus ring on every list.
    await mockApi(page, [COMPLETED_RUN]);
    await page.goto("/#/runs");

    const sortButton = page.getByRole("columnheader", { name: /Run/ }).getByRole("button").first();
    await expect(sortButton).toHaveCSS("border-top-style", "solid");
    await expect(sortButton).toHaveCSS("border-top-width", "0px");
  });
});

test.describe("Run queue — the failed run has a recovery lever (M16 #11)", () => {
  test("a failed run offers Retry, and it reaches POST /runs/{id}/retry", async ({ page }) => {
    // `POST /v1/runs/{id}/retry` has existed since runs did and no UI called it.
    // So the queue offered CANCEL on the two states still moving and *nothing*
    // on the one state that has stopped and needs a decision.
    const retried: string[] = [];
    await mockApi(page, [FAILED_RUN, RUNNING_RUN, COMPLETED_RUN]);
    await page.route("**/api/platform-control/v1/runs/*/retry", (route) => {
      retried.push(new URL(route.request().url()).pathname);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...FAILED_RUN, status: "pending", failure_reason: null }),
      });
    });
    await page.goto("/#/runs");

    const failedRow = page.getByRole("row", { name: /run_failed_1/ });
    await failedRow.getByRole("button", { name: "Retry", exact: true }).click();

    // Retry re-dispatches against the live source, so it is confirmed, not
    // one-click. `ConfirmButton`'s `notable` tier renders a MUI Popover (the
    // `destructive` tier is the one that renders a Dialog), so this asserts on
    // the copy rather than on a dialog role.
    await expect(page.getByText("dispatched again against the live source")).toBeVisible();
    await page.getByRole("button", { name: "Retry run", exact: true }).click();

    await expect.poll(() => retried.length).toBe(1);
    expect(retried[0]).toContain("/v1/runs/run_failed_1/retry");
  });

  test("no run offers both levers, and a completed run offers neither", async ({ page }) => {
    await mockApi(page, [FAILED_RUN, RUNNING_RUN, COMPLETED_RUN]);
    await page.goto("/#/runs");

    const failedRow = page.getByRole("row", { name: /run_failed_1/ });
    await expect(failedRow.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);

    const runningRow = page.getByRole("row", { name: /run_running_1/ });
    await expect(runningRow.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);

    const doneRow = page.getByRole("row", { name: /run_done_1/ });
    await expect(doneRow.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);
    await expect(doneRow.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  });
});

test.describe("Run queue — a stalled run is distinguishable (M16 #1 addendum)", () => {
  test("a still-moving run shows its age, and a long-queued one is flagged", async ({ page }) => {
    // A run queued 30 seconds ago and one stuck three days rendered
    // pixel-identically, and CREATED — the only column that could tell them
    // apart — is clipped off the right edge at 1440px.
    await mockApi(page, [STALE_PENDING_RUN, RUNNING_RUN, COMPLETED_RUN]);
    await page.goto("/#/runs");

    const staleRow = page.getByRole("row", { name: /run_pending_stale/ });
    await expect(staleRow.getByTestId("run-age")).toContainText("queued");
    await expect(staleRow.getByTestId("run-age")).toContainText("check it");

    // A terminal run's age is not still accruing; the CREATED/UPDATED columns
    // are the right place to read one.
    const doneRow = page.getByRole("row", { name: /run_done_1/ });
    await expect(doneRow.getByTestId("run-age")).toHaveCount(0);
  });

  test("the failure reason is legible from the list", async ({ page }) => {
    // It used to `truncate` at "provider returned HT…" — exactly where it starts
    // being useful — forcing a click into the detail page on every failed row.
    await mockApi(page, [FAILED_RUN]);
    await page.goto("/#/runs");

    const reason = page.getByTestId("run-failure-reason");
    await expect(reason).toContainText("HTTP 503 for 2 of 2 captured resources");
    // Rendered height must be more than one line — the clip is what hid the
    // substance.
    const box = await reason.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThan(20);
  });

  test("a completed run does not repeat its badge in prose", async ({ page }) => {
    // Eight identical three-line "Finished successfully. Use the detail view for
    // audit evidence." sentences made the 13-row list 2,230px tall.
    await mockApi(page, [COMPLETED_RUN, RUNNING_RUN]);
    await page.goto("/#/runs");

    await expect(page.getByText("Finished successfully")).toHaveCount(0);
    // The states that are not self-explanatory keep theirs.
    await expect(page.getByText("Active now.")).toBeVisible();
  });
});

test.describe("Run queue — one icon vocabulary (M16 #12)", () => {
  test("the mode badge carries no status glyph, while the state badge does", async ({ page }) => {
    // `pending` wore ⚠ in STATE while `acceptance` wore ⚠ in the mode badge
    // right beside it — one glyph set, two contradictory meanings, adjacent
    // columns. Icons now mean lifecycle status and nothing else; mode keeps its
    // colour (#743) and loses the glyph.
    await mockApi(page, [FAILED_RUN]);
    await page.goto("/#/runs");

    const row = page.getByRole("row", { name: /run_failed_1/ });

    const modeBadge = row.getByText("acceptance", { exact: true });
    await expect(modeBadge).toBeVisible();
    expect(await modeBadge.locator("svg").count()).toBe(0);

    const stateBadge = row.getByText("failed", { exact: true });
    expect(await stateBadge.locator("svg").count()).toBe(1);
  });
});

test.describe("Shell — the dashboard is reachable (M16 #7)", () => {
  test("the sidebar carries an Overview entry and the wordmark links home", async ({ page }) => {
    // All thirteen sidebar links targeted a resource or a create form; none
    // targeted `/`, and the logo was not a link. Leaving the dashboard was
    // one-way.
    await mockApi(page, [COMPLETED_RUN]);
    await page.goto("/#/runs");

    await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
    await page.getByRole("link", { name: /Evidara control plane/ }).click();
    await expect(page).toHaveURL(/#\/$/);
  });
});

test.describe("Shell — dark mode exists (M16 #4)", () => {
  test("the toggle flips the document theme and the page ground with it", async ({ page }) => {
    // Light and dark screenshots of this app were byte-identical (same md5) and
    // the stylesheet held zero `prefers-color-scheme` rules.
    await mockApi(page, [COMPLETED_RUN]);
    await page.goto("/#/runs");

    const html = page.locator("html");
    await expect(html).not.toHaveClass(/\bdark\b/);
    const lightGround = await html.evaluate((el) =>
      getComputedStyle(el).getPropertyValue("--surface-panel").trim(),
    );

    await page.getByTestId("theme-toggle").click();

    await expect(html).toHaveClass(/\bdark\b/);
    await expect(html).toHaveCSS("color-scheme", "dark");
    const darkGround = await html.evaluate((el) =>
      getComputedStyle(el).getPropertyValue("--surface-panel").trim(),
    );
    // The palette actually changed — not merely a class that nothing reads,
    // which is what the app had before (the `.dark` block existed; the class
    // was never applied).
    expect(darkGround).not.toBe(lightGround);
  });

  test("an operator on a dark OS gets dark before first paint", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "dark" });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
    await mockApi(page, [COMPLETED_RUN]);
    await page.goto("/#/runs");

    await expect(page.locator("html")).toHaveClass(/\bdark\b/);
    await context.close();
  });
});

test.describe("Jurisdictions — 2,169 rows are searchable (M16 #8)", () => {
  test("typing a name sends `q` to the server and reports the search's own total", async ({
    page,
  }) => {
    // `/v1/reference-data/jurisdictions` has taken `q` since it was paginated;
    // the admin never sent it, so the only way to reach a row was 44 pages of
    // alphabetical paging.
    const seen: string[] = [];
    await page.route("**/api/platform-control/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [] }),
      }),
    );
    await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) => {
      const url = new URL(route.request().url());
      const q = url.searchParams.get("q");
      seen.push(q ?? "");
      const rows = q
        ? [{ jurisdiction_id: "jur_ch_zh", name: "Zürich", slug: "zh", updated_at: null }]
        : [
            { jurisdiction_id: "jur_ch_ag", name: "Aargau", slug: "ag", updated_at: null },
            { jurisdiction_id: "jur_ch_zh", name: "Zürich", slug: "zh", updated_at: null },
          ];
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: rows,
          total: q ? 1 : 2169,
          limit: 50,
          offset: 0,
        }),
      });
    });

    await page.goto("/#/jurisdictions");
    await expect(page.getByText("2169 jurisdictions")).toBeVisible();

    await page.getByLabel("Search jurisdictions").fill("zür");

    await expect(page.getByText(/1 jurisdiction matching/)).toBeVisible();
    await expect(page.getByText("jur_ch_ag")).toHaveCount(0);
    expect(seen).toContain("zür");
  });
});

test.describe("Blueprints — the futile CTA is demoted (M16 #3)", () => {
  test("a template that needs provider work does not lead with a primary Enable", async ({
    page,
  }) => {
    // The "Needs provider work" filter showed rows reading "Enabling the config
    // key will not unlock it; this needs a provider change" — beside a filled
    // violet Enable, the most prominent affordance on the row.
    await page.route("**/api/platform-control/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [] }),
      }),
    );
    await page.route("**/api/platform-control/v1/sources/blueprint-templates*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              overlay_id: "ch",
              provider_template_id: "canton_http_zh",
              provider: "deterministic_http",
              enabled: false,
              live_ready: true,
              acquisition_readiness: "live",
              launchable: false,
              notes: [],
              default_enabled: false,
              source: "default",
              note: null,
              updated_by: null,
              updated_at: null,
            },
            {
              overlay_id: "de",
              provider_template_id: "bundesland_http_bayern",
              provider: "canton_http",
              enabled: false,
              live_ready: false,
              acquisition_readiness: "scaffold",
              launchable: false,
              notes: [],
              default_enabled: false,
              source: "default",
              note: null,
              updated_by: null,
              updated_at: null,
            },
          ],
        }),
      }),
    );

    await page.goto("/#/blueprint-templates");

    const blockedRow = page.getByRole("row", { name: /bundesland_http_bayern/ });
    await expect(blockedRow.getByTestId("enablement-futility-note")).toContainText(
      "provider needs a change",
    );

    // The one row where enabling finishes the job keeps the filled CTA; the
    // futile one does not. Compared by rendered background so this asserts what
    // an operator actually sees, not a class name.
    const actionable = page
      .getByRole("row", { name: /canton_http_zh/ })
      .getByRole("button", { name: "Enable" });
    const blocked = blockedRow.getByRole("button", { name: "Enable" });
    const actionableBg = await actionable.evaluate((el) => getComputedStyle(el).backgroundColor);
    const blockedBg = await blocked.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(blockedBg).not.toBe(actionableBg);
  });
});
