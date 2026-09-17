import type { Page } from "@playwright/test";
import { pipelineHealth } from "./fixtures/pipelineHealth";
import { expect, test } from "./support/test";

// ---------------------------------------------------------------------------
// Smoke coverage for the ADR-0026 Tailwind port of the preview-approval queue
// (PreviewReviewListV2 / PreviewReviewShowV2). The preview pages are the
// preview-mode slice of the runs surface: the dataProvider forces
// `mode: "preview"` on the list and guards the detail getOne to preview runs.
// This spec drives the canonical `/#/preview-review` routes (v2 consolidated
// onto the resource routes; `/preview-review-v2` redirects), reusing the shared
// operator-action stack and RunDetailSectionsV2.
// ---------------------------------------------------------------------------

const PREVIEW_RUNNING = {
  run_id: "preview_running",
  source_id: "src_1",
  source_version_id: "sv_1",
  source_name: "Swiss Federal Codes",
  version_label: "v1",
  mode: "preview",
  status: "running",
  started_at: "2026-04-15T09:10:00Z",
  completed_at: null,
  artifacts_count: 2,
  captured_resources_count: 8,
  failure_reason: null,
  created_at: "2026-04-15T09:05:00Z",
  updated_at: "2026-04-15T09:20:00Z",
};

const PREVIEW_DONE = {
  run_id: "preview_done",
  source_id: "src_1",
  source_version_id: "sv_1",
  source_name: "Swiss Federal Codes",
  version_label: "v1",
  mode: "preview",
  status: "completed",
  started_at: "2026-04-14T09:00:00Z",
  completed_at: "2026-04-14T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-14T08:55:00Z",
  updated_at: "2026-04-14T09:30:00Z",
};

/**
 * A failed preview run. Before this existed the list was only ever exercised
 * with running and completed runs, which is why it shipped with no Retry: no
 * fixture ever reached the state that needs one.
 */
const PREVIEW_FAILED = {
  ...PREVIEW_DONE,
  run_id: "preview_failed",
  status: "failed",
  completed_at: null,
  failure_reason:
    "Provider returned HTTP 503 for 2 of 2 captured resources, after 3 retries against the upstream host.",
  created_at: "2026-04-15T09:40:00Z",
  updated_at: "2026-04-15T09:41:00Z",
};

const PREVIEW_RUNS = { data: [PREVIEW_RUNNING, PREVIEW_DONE, PREVIEW_FAILED] };

// Minimal-but-valid RunPipelineHealth so RunDetailSectionsV2's banner renders
// (an empty `{ data: [] }` from the catch-all lacks `stages`, which the
// decision-support builder reads → crash).
const PIPELINE_HEALTH = pipelineHealth("preview_running");

async function mockPreviewReviewApi(page: Page) {
  // Benign catch-all first (lowest priority) — sub-resource read models the
  // detail page touches resolve to an empty 200 instead of hanging.
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );

  // Runs list (mode=preview filter is appended by the dataProvider) feeds
  // PreviewReviewListV2.
  await page.route("**/api/platform-control/v1/runs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PREVIEW_RUNS),
    }),
  );

  // Single preview run getOne — raw object with mode "preview" so the
  // dataProvider's preview guard passes. Matched exactly so sub-resource paths
  // fall through to the catch-all.
  await page.route("**/api/platform-control/v1/runs/preview_running", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PREVIEW_RUNNING),
    }),
  );

  // Pipeline-health read model for the detail sections.
  await page.route("**/api/platform-control/v1/runs/*/pipeline-health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PIPELINE_HEALTH),
    }),
  );
}

test.describe("Preview review v2 (ADR-0026 Tailwind port)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("list surfaces the Create Preview Run CTA and opens the launch dialog", async ({ page }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review");

    await page.getByRole("button", { name: "Create Preview Run" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Create Run" })).toBeVisible();
    // Preview-only launch: the Run mode select is disabled (single allowed mode).
    await expect(dialog.getByLabel("Run mode", { exact: true })).toBeDisabled();
  });

  test("running preview run exposes a Cancel row action", async ({ page }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review");

    const runningRow = page.getByRole("row", { name: /preview_running/ });
    await expect(runningRow.getByRole("button", { name: "Cancel" })).toBeVisible();

    const doneRow = page.getByRole("row", { name: /preview_done/ });
    await expect(doneRow.getByRole("button", { name: "Cancel" })).toHaveCount(0);
  });

  test("show renders the operator action stack with Cancel for a running preview run", async ({
    page,
  }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review/preview_running/show");

    await expect(page.getByRole("heading", { name: /Run\s+preview_running/ })).toBeVisible();
    await expect(page.getByText("Operator actions")).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
  });
});

/**
 * The list's ACTIONS column, which shipped off-screen at every width tested.
 *
 * This is the M16 finding (#873) in a third table. The run queue pins its own
 * Actions column; this one did not, and its header was `sr-only` —
 * `position: absolute`, which cannot also be `position: sticky`.
 *
 * Measured before the fix: scrollWidth 1324 against clientWidth 1054 at 1440
 * and 894 at 1280, so the column sat past the right edge of a scroller with no
 * cue. No Vitest layer can see this: jsdom has no layout engine.
 */
test.describe("Preview approvals — the operator's levers survive the fold", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("the Actions column is pinned and no action is cut off at 1280", async ({ page }) => {
    await mockPreviewReviewApi(page);
    await page.setViewportSize({ width: 1280, height: 950 });
    await page.goto("/#/preview-review");

    const header = page.getByRole("columnheader", { name: "Actions" });
    await expect(header).toBeVisible({ timeout: 90_000 });
    // Computed style, not a class name — the assertion jsdom cannot make.
    await expect(header).toHaveCSS("position", "sticky");

    // Measured inside the page, NOT via `locator.boundingBox()`, which scrolls
    // the element into view before measuring and so reveals the very clipping
    // it is asked about.
    const geometry = await page.evaluate(() => {
      const table = document.querySelector("table");
      if (!table) return null;
      const scroller = table.parentElement as HTMLElement;
      const buttons = [...table.querySelectorAll("tbody tr td:last-child button")].map((b) => ({
        label: (b.textContent ?? "").trim(),
        right: Math.round(b.getBoundingClientRect().right),
      }));
      return {
        scrollLeft: scroller.scrollLeft,
        overflows: scroller.scrollWidth > scroller.clientWidth + 1,
        visibleRight: Math.min(
          Math.round(scroller.getBoundingClientRect().right),
          window.innerWidth,
        ),
        buttons,
      };
    });

    expect(geometry, "the preview list table did not render").not.toBeNull();
    // Guard against the guard: without overflow there is nothing to measure and
    // the assertions below would pass vacuously. Fail loudly instead.
    expect(geometry!.overflows, "table no longer overflows at 1280 — retune this test").toBe(true);
    expect(geometry!.scrollLeft, "test scrolled the table before measuring").toBe(0);
    expect(geometry!.buttons.length).toBeGreaterThan(0);

    for (const button of geometry!.buttons) {
      expect(
        button.right,
        `"${button.label}" is cut off at x=${button.right}, past the visible edge x=${geometry!.visibleRight}`,
      ).toBeLessThanOrEqual(geometry!.visibleRight);
    }
  });

  test("a failed preview run offers Retry from the list, as the run queue does", async ({
    page,
  }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review");

    // The same run in `#/runs` offers Retry. Offering it there and not here
    // makes the two screens disagree about what the operator can do.
    const failedRow = page.getByRole("row", { name: /preview_failed/ });
    await expect(failedRow).toBeVisible({ timeout: 90_000 });
    await expect(failedRow.getByRole("button", { name: /retry/i })).toBeVisible();

    // Cancel is for pending/running, so a failed run must not offer it — no
    // state offers both levers.
    await expect(failedRow.getByRole("button", { name: /cancel/i })).toHaveCount(0);
  });
});
