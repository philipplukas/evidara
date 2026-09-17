import type { Page } from "@playwright/test";
import { pipelineHealth } from "./fixtures/pipelineHealth";
import { expect, test } from "./support/test";

// ---------------------------------------------------------------------------
// Smoke coverage for the ADR-0026 runs v2 parity slice: the operator-action
// stack and keyboard shortcuts wired into `RunListV2` / `RunShowV2` using the
// now-Tailwind action components (RunLaunchButton, CancelRunButton,
// RunActionStack) plus the legal-search RunHandoffCard. Drives the canonical
// canonical `/#/runs` routes (v2 consolidated onto `/runs`; `/runs-v2` redirects).
// ---------------------------------------------------------------------------

const RUN_RUNNING = {
  run_id: "run_running",
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

const RUN_DONE = {
  run_id: "run_done",
  source_id: "src_1",
  source_version_id: "sv_1",
  source_name: "Swiss Federal Codes",
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

const RUNS = { data: [RUN_RUNNING, RUN_DONE] };

// Minimal-but-valid RunPipelineHealth so RunDetailSectionsV2's banner renders
// (an empty `{ data: [] }` from the catch-all lacks `stages`, which the
// decision-support builder reads → crash).
const PIPELINE_HEALTH = pipelineHealth("run_running");

async function mockRunsApi(page: Page) {
  // Benign catch-all first (lowest priority) — RunDetailSectionsV2 and other
  // read models the v2 pages touch resolve to an empty 200 instead of hanging.
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );

  // Runs list feeds RunListV2.
  await page.route("**/api/platform-control/v1/runs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(RUNS),
    }),
  );

  // Single-run getOne feeds RunShowV2 (raw object, not `{ data }`). Registered
  // after the list route and matched exactly so sub-resource paths fall through
  // to the catch-all.
  await page.route("**/api/platform-control/v1/runs/run_running", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(RUN_RUNNING),
    }),
  );

  // Pipeline-health read model for the RunShowV2 detail sections.
  await page.route("**/api/platform-control/v1/runs/*/pipeline-health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PIPELINE_HEALTH),
    }),
  );
}

test.describe("Runs v2 parity (ADR-0026 operator-action stack)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("list surfaces the Create Run CTA and opens the launch dialog", async ({ page }) => {
    await mockRunsApi(page);
    await page.goto("/#/runs");

    // The header CTA is the ported RunLaunchButton.
    await page.getByRole("button", { name: "Create Run" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Create Run" })).toBeVisible();
  });

  test("running run exposes a Cancel row action", async ({ page }) => {
    await mockRunsApi(page);
    await page.goto("/#/runs");

    // CancelRunButton renders only for pending/running runs — the running row
    // shows it, the completed row does not.
    const runningRow = page.getByRole("row", { name: /run_running/ });
    await expect(runningRow.getByRole("button", { name: "Cancel" })).toBeVisible();

    const doneRow = page.getByRole("row", { name: /run_done/ });
    await expect(doneRow.getByRole("button", { name: "Cancel" })).toHaveCount(0);
  });

  test("pressing O opens the attention run detail", async ({ page }) => {
    await mockRunsApi(page);
    await page.goto("/#/runs");

    // Wait for the queue to render before firing the shortcut.
    await expect(page.getByText("run_running").first()).toBeVisible();
    await page.keyboard.press("o");

    await expect(page).toHaveURL(/#\/runs\/run_running\/show/);
    await expect(page.getByRole("heading", { name: /Run\s+run_running/ })).toBeVisible();
  });

  test("show renders the operator action stack with Cancel for a running run", async ({ page }) => {
    await mockRunsApi(page);
    await page.goto("/#/runs/run_running/show");

    // RunActionStack renders its "Operator actions" panel with the Cancel CTA
    // for a running run.
    await expect(page.getByText("Operator actions")).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
  });

  test("show renders the legal-search handoff card when handoff params are present", async ({
    page,
  }) => {
    await mockRunsApi(page);
    // Handoff context is read from window.location.search (before the hash).
    await page.goto(
      "/?from=legal-search&ls_query=data+protection&ls_item=doc_42#/runs/run_running/show",
    );

    await expect(page.getByRole("heading", { name: "Legal search handoff" })).toBeVisible();
    // The query surfaces as its own summary Pill (exact match — the narrative
    // copy repeats the query, so a substring match would be ambiguous).
    await expect(page.getByText("data protection", { exact: true })).toBeVisible();
  });
});
