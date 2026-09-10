/**
 * Blueprint coverage inventory + config-key flip (#668).
 *
 * The regression this guards is not a rendering detail — it is that
 * `setBlueprintTemplateEnablement` shipped with **zero UI callers**, so the
 * `enabled: true` step of the #628 coverage loop had no screen and the panel
 * told operators to issue a `PUT` by hand. The load-bearing assertions are
 * therefore: the inventory exists and is reachable from the sidebar; it makes
 * the two keys distinguishable; and the enable action actually reaches the
 * endpoint with the operator's evidence note attached.
 */
import { expect, type Page, test } from "@playwright/test";

// Three templates, one per lock class, so every branch of `classifyTemplate`
// renders: live (both keys), operator-actionable (config key shut, provider
// ready), engineer-blocked (code key shut).
const BLUEPRINT_TEMPLATES = {
  data: [
    {
      overlay_id: "ch",
      provider_template_id: "fedlex-default",
      provider: "fedlex_sparql",
      enabled: true,
      live_ready: true,
      acquisition_readiness: "live",
      launchable: true,
      notes: [],
      default_enabled: true,
      source: "default",
      note: null,
      updated_by: null,
      updated_at: null,
    },
    {
      overlay_id: "ch",
      provider_template_id: "canton_http_zh",
      provider: "deterministic_http",
      enabled: false,
      live_ready: true,
      acquisition_readiness: "live",
      launchable: false,
      notes: [
        "Config key closed: not enabled. Capture acceptance-run evidence, then enable this template to launch live runs (ADR-0030).",
      ],
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
      notes: [
        "Code key closed: provider 'canton_http' cannot acquire this format yet — it is a scaffold or faces sources it cannot fetch. This needs engineering (ADR-0030).",
        "Config key closed: not enabled. Capture acceptance-run evidence, then enable this template to launch live runs (ADR-0030).",
      ],
      default_enabled: false,
      source: "default",
      note: null,
      updated_by: null,
      updated_at: null,
    },
    {
      // Built and verified, but unproven — the state that used to be reported as a
      // scaffold, sending operators to an engineer for work already done (#743).
      overlay_id: "ch",
      provider_template_id: "gemeinde_http_zh_stadt_hundevorschriften",
      provider: "gemeinde_http",
      enabled: false,
      live_ready: false,
      acquisition_readiness: "awaiting_evidence",
      launchable: false,
      notes: [
        "Code key closed: provider 'gemeinde_http' is implemented and verified, but no acceptance run has been captured for it yet. You can capture it yourself: run the acceptance harness against the live source (a run with mode=acceptance). Moving the provider to 'live' afterwards is still a code change, so attach the evidence to that request (ADR-0030).",
        "Config key closed: not enabled. Capture acceptance-run evidence, then enable this template to launch live runs (ADR-0030).",
      ],
      default_enabled: false,
      source: "default",
      note: null,
      updated_by: null,
      updated_at: null,
    },
  ],
};

async function mockBlueprintApi(page: Page) {
  /*
   * Benign catch-all, registered FIRST so it has the lowest priority — Playwright
   * matches handlers in reverse registration order, so every specific route below
   * still wins.
   *
   * It is not belt-and-braces. `src/middleware.ts` REWRITES
   * `/api/platform-control/*` to `PLATFORM_CONTROL_API_URL`, defaulting to
   * `http://127.0.0.1:8000` — and the `Admin e2e (Playwright)` CI job starts no
   * backend, because the specs are supposed to mock everything. So a single
   * request these specs do not name does not fail politely: it escapes to a dead
   * port, comes back `ECONNREFUSED` → 500, and the view never renders. The test
   * then reports "element(s) not found", which reads as a missing element rather
   * than a failed fetch.
   *
   * Six of the nine admin specs already do this. These three did not.
   */
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );

  const enablementCalls: Array<{ url: string; body: unknown }> = [];

  await page.route(
    "**/api/platform-control/v1/sources/blueprint-templates/*/*/enablement",
    async (route) => {
      const url = route.request().url();
      const body = JSON.parse(route.request().postData() ?? "{}");
      enablementCalls.push({ url, body });
      // Reflect the flip back the way the API does, including the audit trail.
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          overlay_id: "ch",
          provider_template_id: "canton_http_zh",
          enabled: (body as { enabled: boolean }).enabled,
          default_enabled: false,
          source: "override",
          note: (body as { note: string | null }).note,
          updated_by: "op_00000000000000000000000001",
          updated_at: "2026-07-19T10:00:00Z",
          // The dialog reports on `applied` — the server's read-back — not on the
          // status code, so the mock has to carry it (#631, #713, #854).
          applied: true,
          needs_human: false,
          needs_human_reasons: [],
          evidence_binding: "template",
        }),
      });
    },
  );

  await page.route("**/api/platform-control/v1/sources/blueprint-templates*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BLUEPRINT_TEMPLATES),
    }),
  );

  return { getEnablementCalls: () => enablementCalls };
}

test.describe("Blueprint coverage inventory", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("is reachable from the sidebar and lists every template with its lock state", async ({
    page,
  }) => {
    await mockBlueprintApi(page);
    await page.goto("/#/sources");

    // Scoped to the sidebar, which is what this test's name claims to check.
    // Sources and Blueprints are siblings in the BUILD nav group, so the group's
    // tab strip renders a second "Blueprints" link on this page — an unscoped
    // locator matches both and fails strict mode.
    await page.getByLabel("Primary navigation").getByRole("link", { name: "Blueprints" }).click();

    await expect(page.locator("h1")).toContainText("Blueprints");
    await expect(page.getByText("fedlex-default")).toBeVisible();
    await expect(page.getByText("canton_http_zh")).toBeVisible();
    await expect(page.getByText("bundesland_http_bayern")).toBeVisible();
  });

  test("distinguishes the key an operator owns from the key that needs an engineer", async ({
    page,
  }) => {
    await mockBlueprintApi(page);
    await page.goto("/#/blueprint-templates");
    await expect(page.locator("h1")).toContainText("Blueprints");

    // The operator-actionable template says the shut key is theirs to turn…
    const actionableRow = page.getByRole("row", { name: /canton_http_zh/ });
    await expect(actionableRow).toContainText("Ready to enable");
    await expect(actionableRow).toContainText("yours to turn");

    // …while the engineer-blocked one names the provider as the blocker and
    // never tells the operator the fix is theirs.
    const blockedRow = page.getByRole("row", { name: /bundesland_http_bayern/ });
    await expect(blockedRow).toContainText("Needs provider work");
    await expect(blockedRow).toContainText("needs an engineer");
  });

  test("a built-but-unproven provider is not reported as needing an engineer", async ({ page }) => {
    // #743: `live_ready: false` used to mean "scaffold" unconditionally, so this
    // row read "Needs provider work" for a provider that acquires and normalises
    // its format today. The operator was sent to build something that existed.
    await mockBlueprintApi(page);
    await page.goto("/#/blueprint-templates");

    const row = page.getByRole("row", { name: /gemeinde_http_zh_stadt_hundevorschriften/ });
    await expect(row).toContainText("Awaiting acceptance run");
    await expect(row).not.toContainText("Needs provider work");
    await expect(row).not.toContainText("needs an engineer");
    // The remedy, and that it is the operator's to take.
    await expect(row).toContainText("capture evidence with the harness");
  });

  test("the 'awaiting evidence' preset filters to the operator's own worklist", async ({
    page,
  }) => {
    await mockBlueprintApi(page);
    await page.goto("/#/blueprint-templates");

    await page.getByRole("button", { name: /Ready to enable/ }).click();

    await expect(page.getByText("canton_http_zh")).toBeVisible();
    await expect(page.getByText("bundesland_http_bayern")).toHaveCount(0);
    await expect(page.getByText("fedlex-default")).toHaveCount(0);
  });

  test("an operator can flip the config key, and only with a cited run", async ({ page }) => {
    const mocks = await mockBlueprintApi(page);
    await page.goto("/#/blueprint-templates");

    const actionableRow = page.getByRole("row", { name: /canton_http_zh/ });
    await actionableRow.getByRole("button", { name: "Enable" }).click();

    const dialog = page.getByTestId("blueprint-enablement-dialog");
    await expect(dialog).toBeVisible();

    const submit = dialog.getByRole("button", { name: "Enable template" });
    await expect(submit).toBeDisabled();

    // A note ALONE used to arm the key here, which is precisely what made this
    // panel the soft path around ADR-0030 (#854): an operator refused by the CLI
    // could type one character into this box and get the same state. It must not
    // be enough on its own.
    await dialog.getByLabel("Evidence note").fill("acceptance run r_01J: 42/42 acts parsed");
    await expect(submit).toBeDisabled();

    await dialog.getByLabel("Acceptance run id").fill("run_01J");
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(dialog).toBeHidden();

    const calls = mocks.getEnablementCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/blueprint-templates/ch/canton_http_zh/enablement");
    // The guard is server-side now, so what matters is that the panel actually
    // sends its inputs — a PUT of `{enabled, note}` alone cannot be guarded.
    expect(calls[0].body).toEqual({
      enabled: true,
      note: "acceptance run r_01J: 42/42 acts parsed",
      evidence_run_id: "run_01J",
      reopen_operator_kill_switch: false,
      acknowledge_provider_below_live: false,
    });
  });

  test("warns that enabling will not unlock a template whose code key is shut", async ({
    page,
  }) => {
    await mockBlueprintApi(page);
    await page.goto("/#/blueprint-templates");

    const blockedRow = page.getByRole("row", { name: /bundesland_http_bayern/ });
    await blockedRow.getByRole("button", { name: "Enable" }).click();

    const dialog = page.getByTestId("blueprint-enablement-dialog");
    await expect(dialog.getByTestId("blueprint-enablement-code-key-warning")).toContainText(
      "will not make the template launchable",
    );
  });
});
