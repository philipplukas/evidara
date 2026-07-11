import { expect, type Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Smoke coverage for the ADR-0026 Tailwind port of the run-launch dialog
// (RunLaunchDialog.tsx) + operator-action stack. The dialog now renders on
// the `<Dialog>` primitive with Panel/Pill/InlineAlert chrome and native
// <select>s (it holds inputs in local state, so the useInput-bound `Select`
// primitive doesn't apply). This spec drives it through the canonical /runs
// list, the same surface an operator uses.
// ---------------------------------------------------------------------------

const RUNS = {
  data: [
    {
      run_id: "run_1",
      source_id: "src_1",
      source_version_id: "sv_1",
      mode: "production",
      status: "completed",
      started_at: "2026-04-15T09:00:00Z",
      completed_at: "2026-04-15T09:30:00Z",
      artifacts_count: 4,
      captured_resources_count: 12,
      failure_reason: null,
      created_at: "2026-04-15T08:55:00Z",
      updated_at: "2026-04-15T09:30:00Z",
    },
  ],
};

const SOURCES = {
  data: [
    {
      source_id: "src_1",
      name: "Swiss Federal Codes",
      description: "Test source",
      jurisdiction_id: "jur_ch",
      authority_id: "auth_fedlex",
      source_type: "website",
      document_family: null,
      enabled: true,
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

const SOURCE_VERSIONS = {
  data: [
    {
      source_version_id: "sv_1",
      source_id: "src_1",
      version_label: "v1",
      status: "approved",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

const READINESS_READY = { ready: true, checks: [] };

async function mockRunLaunchApi(page: Page) {
  // Benign catch-all registered first (lowest priority). Any platform-control
  // endpoint the v1 list touches but that this smoke doesn't care about
  // (pipeline-health probes, etc.) resolves to an empty 200 instead of
  // hanging on the network.
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );

  // Runs list (also serves the attention-run preview query — same handler).
  await page.route("**/api/platform-control/v1/runs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(RUNS),
    }),
  );

  // Preflight readiness — registered after the runs route so it wins for
  // `/v1/runs/readiness?...`.
  await page.route("**/api/platform-control/v1/runs/readiness*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(READINESS_READY),
    }),
  );

  // Sources list feeds the dialog's source picker.
  await page.route("**/api/platform-control/v1/sources*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SOURCES),
    }),
  );

  // Per-source versions — registered last so it wins over the sources route.
  await page.route("**/api/platform-control/v1/sources/*/versions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SOURCE_VERSIONS),
    }),
  );
}

test.describe("Run launch dialog (ADR-0026 Tailwind port)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("opens on the Dialog primitive and drives preflight to ready", async ({ page }) => {
    await mockRunLaunchApi(page);

    await page.goto("/#/runs");

    // Open the launch dialog from the run-queue CTA.
    await page.getByRole("button", { name: "Create Run" }).first().click();

    // The ported chrome: a role=dialog with the primitive's <h2> title.
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Create Run" })).toBeVisible();

    // Launch summary Pills render (mode + the "not selected" placeholders).
    await expect(dialog.getByText("Production mode")).toBeVisible();
    await expect(dialog.getByText("Source not selected")).toBeVisible();

    // The three FormField-wrapped native selects are reachable by label
    // (scoped to the dialog — the v1 list has its own "Run mode" filter).
    await expect(dialog.getByLabel("Run mode", { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Source", { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Source version", { exact: true })).toBeVisible();

    // Create is gated until a ready source/version pair is picked.
    const createButton = dialog.getByRole("button", { name: "Create Run" });
    await expect(createButton).toBeDisabled();

    // Pick the source, then its approved version.
    await dialog
      .getByLabel("Source", { exact: true })
      .selectOption({ label: "Swiss Federal Codes" });
    await dialog
      .getByLabel("Source version", { exact: true })
      .selectOption({ label: "v1 (approved)" });

    // Preflight resolves ready → the success InlineAlert shows and Create unlocks.
    await expect(
      dialog.getByText("The current source/version pair is ready to launch."),
    ).toBeVisible();
    await expect(createButton).toBeEnabled();
  });

  test("Cancel closes the dialog without creating a run", async ({ page }) => {
    await mockRunLaunchApi(page);

    await page.goto("/#/runs");
    await page.getByRole("button", { name: "Create Run" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  });
});
