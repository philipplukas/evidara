import { expect, type Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Smoke coverage for the ADR-0026 Tailwind port of the preview-approval queue
// (PreviewReviewListV2 / PreviewReviewShowV2). The preview pages are the
// preview-mode slice of the runs surface: the dataProvider forces
// `mode: "preview"` on the list and guards the detail getOne to preview runs.
// This spec drives the canonical `/#/preview-review-v2` preview routes, reusing
// the shared operator-action stack and RunDetailSectionsV2.
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

const PREVIEW_RUNS = { data: [PREVIEW_RUNNING, PREVIEW_DONE] };

// Minimal-but-valid RunPipelineHealth so RunDetailSectionsV2's banner renders
// (an empty `{ data: [] }` from the catch-all lacks `stages`, which the
// decision-support builder reads → crash).
const PIPELINE_HEALTH = {
  run_id: "preview_running",
  source_id: "src_1",
  source_version_id: "sv_1",
  mode: "preview",
  run_status: "running",
  overall_status: "in_progress",
  stages: [],
  processing_status_event_count: 0,
  document_lifecycle_event_count: 0,
};

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
    await page.goto("/#/preview-review-v2");

    await page.getByRole("button", { name: "Create Preview Run" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Create Run" })).toBeVisible();
    // Preview-only launch: the Run mode select is disabled (single allowed mode).
    await expect(dialog.getByLabel("Run mode", { exact: true })).toBeDisabled();
  });

  test("running preview run exposes a Cancel row action", async ({ page }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review-v2");

    const runningRow = page.getByRole("row", { name: /preview_running/ });
    await expect(runningRow.getByRole("button", { name: "Cancel" })).toBeVisible();

    const doneRow = page.getByRole("row", { name: /preview_done/ });
    await expect(doneRow.getByRole("button", { name: "Cancel" })).toHaveCount(0);
  });

  test("show renders the operator action stack with Cancel for a running preview run", async ({
    page,
  }) => {
    await mockPreviewReviewApi(page);
    await page.goto("/#/preview-review-v2/preview_running");

    await expect(page.getByRole("heading", { name: /Run\s+preview_running/ })).toBeVisible();
    await expect(page.getByText("Operator actions")).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
  });
});
