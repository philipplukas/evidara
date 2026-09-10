import { expect, type Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixture data — mirrors the shapes the platform-control API returns
// ---------------------------------------------------------------------------

const JURISDICTIONS = {
  data: [
    {
      jurisdiction_id: "jur_ch",
      name: "Switzerland",
      slug: "ch",
      parent_id: null,
      compliance_policy_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      jurisdiction_id: "jur_at",
      name: "Austria",
      slug: "at",
      parent_id: null,
      compliance_policy_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

const AUTHORITIES = {
  data: [
    {
      authority_id: "auth_fedlex",
      jurisdiction_id: "jur_ch",
      name: "Fedlex",
      slug: "fedlex",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      authority_id: "auth_ris",
      jurisdiction_id: "jur_at",
      name: "RIS",
      slug: "ris",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      authority_id: "auth_global",
      jurisdiction_id: null,
      name: "Global Authority",
      slug: "global",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

// Flat blueprint-template list — one template per overlay.
//
// Every template and preview carries the ADR-0030 two-key lock
// (`enabled` / `live_ready` / `launchable` / `notes`); the API always emits all
// four (see `SourceBlueprintTemplateResponse` / `SourceBlueprintPreviewResponse`
// in `platform-control/src/platform_control/schemas/source.py`). Omitting them
// here is not a "smaller" fixture — it is a shape the server never returns, and
// it crashes the preview panel. CH is launchable, AT is inert (config key off)
// so the "· inert (locked)" choice marker is covered too.
const BLUEPRINT_TEMPLATES = {
  data: [
    {
      overlay_id: "ch",
      provider_template_id: "fedlex-default",
      provider: "fedlex_sparql",
      enabled: true,
      live_ready: true,
      launchable: true,
      notes: [],
    },
    {
      overlay_id: "at",
      provider_template_id: "ris-default",
      provider: "ris_ogd",
      enabled: false,
      live_ready: true,
      launchable: false,
      notes: ["Config key is off — an operator has not enabled this template yet."],
    },
  ],
};

// Server-expanded acquisition spec preview for the CH / fedlex template.
const BLUEPRINT_PREVIEW = {
  overlay_id: "ch",
  provider_template_id: "fedlex-default",
  acquisition_spec: {
    provider: "fedlex_sparql",
    seed_url: "https://fedlex.example/eli/work-a",
    seed_urls: ["https://fedlex.example/eli/work-b"],
    sparql_endpoint: "https://fedlex.example/sparql",
    preferred_languages: ["de", "fr"],
    query_mode: "work_to_expression",
    max_expressions: 25,
  },
  enabled: true,
  live_ready: true,
  launchable: true,
  notes: [],
};

// Same shape for the AT / RIS template, but with the config key still closed —
// the two-key lock must warn instead of promising a live run (#634).
const INERT_BLUEPRINT_PREVIEW = {
  overlay_id: "at",
  provider_template_id: "ris-default",
  acquisition_spec: {
    provider: "ris_ogd",
    base_url: "https://ris.example/api",
    applikation: "Bundesnormen",
    preferred_formats: ["html"],
    page_size: 100,
    max_pages: 5,
  },
  enabled: false,
  live_ready: true,
  launchable: false,
  notes: ["Config key is off — an operator has not enabled this template yet."],
};

const CREATED_SOURCE = {
  source_id: "src_test_001",
  name: "Swiss Federal Codes",
  description: "Test source for e2e",
  jurisdiction_id: "jur_ch",
  authority_id: "auth_fedlex",
  source_type: "website",
  document_family: null,
  enabled: true,
  status: "active",
  created_at: "2026-04-22T00:00:00Z",
  updated_at: "2026-04-22T00:00:00Z",
};

// The `POST /v1/sources/with-version` response — source + its initial version.
const CREATED_WITH_VERSION = {
  source: CREATED_SOURCE,
  source_version: {
    source_version_id: "sv_test_001",
    source_id: "src_test_001",
    version_label: "v1",
    status: "draft",
    created_at: "2026-04-22T00:00:00Z",
    updated_at: "2026-04-22T00:00:00Z",
  },
};

// ---------------------------------------------------------------------------
// API mock setup — intercepts /api/platform-control/* at the browser level
// ---------------------------------------------------------------------------

async function mockPlatformControlApi(page: Page) {
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

  /** Captured `with-version` create payload for assertions. */
  let capturedCreatePayload: Record<string, unknown> | null = null;

  // Jurisdictions
  await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(JURISDICTIONS),
    }),
  );

  // Authorities
  await page.route("**/api/platform-control/v1/reference-data/authorities*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(AUTHORITIES),
    }),
  );

  // General sources endpoint (list + individual GET after redirect). Registered
  // FIRST so the more-specific blueprint / with-version routes below take
  // precedence — Playwright checks the most-recently-registered handler first.
  await page.route("**/api/platform-control/v1/sources*", async (route) => {
    const url = route.request().url();
    if (url.includes("/sources/src_test_001")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CREATED_SOURCE),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [CREATED_SOURCE] }),
    });
  });

  // Blueprint template list.
  await page.route("**/api/platform-control/v1/sources/blueprint-templates*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BLUEPRINT_TEMPLATES),
    }),
  );

  // Server-side blueprint preview. Answers per requested overlay so the inert
  // (locked) AT template can be asserted alongside the launchable CH one.
  await page.route("**/api/platform-control/v1/sources/blueprint-preview*", (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}") as { overlay_id?: string };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body.overlay_id === "at" ? INERT_BLUEPRINT_PREVIEW : BLUEPRINT_PREVIEW),
    });
  });

  // Combined source + initial-version create.
  await page.route("**/api/platform-control/v1/sources/with-version*", async (route) => {
    capturedCreatePayload = JSON.parse(route.request().postData() ?? "{}");
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(CREATED_WITH_VERSION),
    });
  });

  return {
    getCapturedPayload: () => capturedCreatePayload,
  };
}

// ---------------------------------------------------------------------------
// Helpers for interacting with radix selects
// ---------------------------------------------------------------------------

/** Open a radix Select by its label, pick an option by visible text. */
async function pickRadixSelect(page: Page, label: string, optionText: string) {
  const trigger = page.getByRole("combobox", { name: label }).first();
  await expect(trigger).toBeVisible();
  await trigger.click();

  // Radix portals the listbox to document.body
  const option = page.getByRole("option", { name: optionText });
  await option.click();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("SourceCreate wizard", () => {
  test.beforeEach(async ({ page }) => {
    // Set role so the auth gate lets us through
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("full wizard flow: fill form, preview, submit source + version payload", async ({
    page,
  }) => {
    const mocks = await mockPlatformControlApi(page);

    // react-admin uses hash routing by default
    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    // ── Source metadata ──
    await page.getByLabel("Name").fill("Swiss Federal Codes");
    await page.getByLabel("Description").fill("Test source for e2e");
    await pickRadixSelect(page, "Jurisdiction", "Switzerland (ch)");
    await pickRadixSelect(page, "Authority", "Fedlex (fedlex)");

    // ── Overlay + provider template ──
    await pickRadixSelect(page, "Country overlay", "Switzerland (CH)");
    await pickRadixSelect(page, "Provider template", "fedlex-default (fedlex_sparql)");

    // ── The server-side blueprint preview renders the expanded spec ──
    const preview = page.getByTestId("blueprint-preview");
    await expect(preview).toContainText("Provider: fedlex_sparql");
    await expect(preview).toContainText("SPARQL endpoint: https://fedlex.example/sparql");

    // ── Both ADR-0030 keys are open, so the lock panel clears the run ──
    const lock = page.getByTestId("blueprint-lock");
    await expect(lock).toContainText("this template can launch live runs");
    await expect(lock).toContainText("Config key (enabled): on");
    await expect(lock).toContainText("Code key (readiness): on");

    // ── Submit ──
    await page.getByRole("button", { name: "Create source" }).click();

    // The captured payload matches the source-create-wizard contract.
    await expect.poll(() => mocks.getCapturedPayload(), { timeout: 5000 }).toBeTruthy();
    const payload = mocks.getCapturedPayload()!;
    expect(payload).toMatchObject({
      source: {
        name: "Swiss Federal Codes",
        description: "Test source for e2e",
        jurisdiction_id: "jur_ch",
        authority_id: "auth_fedlex",
        source_type: "website",
      },
      source_version: {
        version_label: "v1",
        overlay_id: "ch",
        provider_template_id: "fedlex-default",
      },
    });
  });

  test("authority select filters when jurisdiction changes", async ({ page }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    // Pick Switzerland — should show Fedlex + Global Authority
    await pickRadixSelect(page, "Jurisdiction", "Switzerland (ch)");

    const authorityTrigger = page.getByRole("combobox", { name: "Authority" }).first();
    await authorityTrigger.click();
    await expect(page.getByRole("option", { name: "Fedlex (fedlex)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Global Authority (global)" })).toBeVisible();
    // RIS (Austrian) should NOT be visible
    await expect(page.getByRole("option", { name: "RIS (ris)" })).toBeHidden();
    await page.keyboard.press("Escape");

    // Switch to Austria — should show RIS + Global Authority
    await pickRadixSelect(page, "Jurisdiction", "Austria (at)");

    const authorityTrigger2 = page.getByRole("combobox", { name: "Authority" }).first();
    await authorityTrigger2.click();
    await expect(page.getByRole("option", { name: "RIS (ris)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Global Authority (global)" })).toBeVisible();
    // Fedlex (Swiss) should NOT be visible
    await expect(page.getByRole("option", { name: "Fedlex (fedlex)" })).toBeHidden();
  });

  test("provider template choices are gated on the picked country overlay", async ({ page }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    // Pick the CH overlay — only its template should be offered.
    await pickRadixSelect(page, "Country overlay", "Switzerland (CH)");
    const templateTrigger = page.getByRole("combobox", { name: "Provider template" }).first();
    await templateTrigger.click();
    await expect(
      page.getByRole("option", { name: "fedlex-default (fedlex_sparql)" }),
    ).toBeVisible();
    // The AT template must not appear under the CH overlay.
    await expect(page.getByRole("option", { name: "ris-default (ris_ogd)" })).toBeHidden();
    await page.keyboard.press("Escape");

    // Switch to AT overlay — the template select remounts with the AT template.
    await pickRadixSelect(page, "Country overlay", "Austria (AT)");
    const templateTrigger2 = page.getByRole("combobox", { name: "Provider template" }).first();
    await templateTrigger2.click();
    await expect(page.getByRole("option", { name: "ris-default (ris_ogd)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "fedlex-default (fedlex_sparql)" })).toBeHidden();
  });

  test("an inert template is flagged at selection time, before the operator invests", async ({
    page,
  }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    // The closed config key is visible in the choice label itself (#634) — the
    // operator sees the lock while picking, not four green steps later.
    await pickRadixSelect(page, "Country overlay", "Austria (AT)");
    const templateTrigger = page.getByRole("combobox", { name: "Provider template" }).first();
    await templateTrigger.click();
    await expect(
      page.getByRole("option", { name: "ris-default (ris_ogd) · inert (locked)" }),
    ).toBeVisible();
    await page.getByRole("option", { name: "ris-default (ris_ogd) · inert (locked)" }).click();

    // …and the preview panel warns rather than promising a live run.
    const lock = page.getByTestId("blueprint-lock");
    await expect(lock).toContainText("Inert template — the two-key lock will block live runs");
    await expect(lock).toContainText("Config key (enabled): off");
    await expect(lock).toContainText("Code key (readiness): on");
    await expect(lock).toContainText("an operator has not enabled this template yet");
  });

  test("blueprint preview raw-JSON toggle reveals the expanded acquisition_spec", async ({
    page,
  }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    await pickRadixSelect(page, "Country overlay", "Switzerland (CH)");
    await pickRadixSelect(page, "Provider template", "fedlex-default (fedlex_sparql)");

    const preview = page.getByTestId("blueprint-preview");
    await expect(preview).toContainText("Provider: fedlex_sparql");

    // Raw JSON is hidden until toggled.
    await expect(preview.locator("pre")).toBeHidden();
    await preview.getByRole("button", { name: "Show raw JSON" }).click();
    await expect(preview.locator("pre")).toContainText('"provider": "fedlex_sparql"');
    await expect(preview.locator("pre")).toContainText("sparql_endpoint");

    // Toggling again hides it.
    await preview.getByRole("button", { name: "Hide raw JSON" }).click();
    await expect(preview.locator("pre")).toBeHidden();
  });
});

/**
 * #666 — the milestone-blocking one.
 *
 * The picker fetched 250 of 2,169 jurisdictions into a native `<select>`, cut
 * alphabetically at "Bovernier". `jur_ch_zh` (ADR-0033's dog jurisdiction) and
 * `jur_ch_federal` (the canary in `scripts/ch-fedlex-fast-loop.sh`) were both
 * past the cut, so an operator could not create a source for either — none of
 * the four sources that already existed could have been made in this wizard.
 *
 * The fixture reproduces the real registry's shape: enough alphabetically-early
 * entries to push the interesting ids well outside any fixed window.
 */
test.describe("SourceCreate jurisdiction reachability (#666)", () => {
  const BIG_REGISTRY = {
    data: [
      ...Array.from({ length: 2167 }, (_, index) => ({
        jurisdiction_id: `jur_gem_${index}`,
        // "Aa…"/"Bo…" names sort ahead of Zürich and Swiss Confederation.
        name: `Aargau Gemeinde ${String(index).padStart(4, "0")}`,
        slug: `ch-gemeinde-${index}`,
        parent_id: null,
        compliance_policy_id: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      })),
      {
        jurisdiction_id: "jur_ch_zh",
        name: "Kanton Zürich",
        slug: "ch-zh",
        parent_id: null,
        compliance_policy_id: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        jurisdiction_id: "jur_ch_federal",
        name: "Swiss Confederation",
        slug: "ch-federal",
        parent_id: null,
        compliance_policy_id: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
  };

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("Zürich and the federal jurisdiction are reachable in a 2169-entry registry", async ({
    page,
  }) => {
    await mockPlatformControlApi(page);
    // Override the small fixture with a realistically-sized registry.
    await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(BIG_REGISTRY),
      }),
    );

    await page.goto("/#/sources/create");
    await expect(page.locator("h1")).toContainText("Create source");

    const picker = page.getByTestId("source-jurisdiction-combobox");
    const input = picker.getByRole("combobox");
    await input.click();

    // The option list is windowed — but it says so, rather than looking complete.
    await expect(picker.locator("p[aria-live]")).toContainText("of 2169 matches");

    // The dog jurisdiction, found by typing its ASCII spelling.
    await input.fill("zurich");
    const zurich = page.getByRole("option", { name: "Kanton Zürich (ch-zh)" });
    await expect(zurich).toBeVisible();
    await zurich.click();
    await expect(input).toHaveValue("Kanton Zürich (ch-zh)");

    // The canary jurisdiction, found by pasting its id.
    await input.click();
    await input.fill("jur_ch_federal");
    const federal = page.getByRole("option", { name: "Swiss Confederation (ch-federal)" });
    await expect(federal).toBeVisible();
    await federal.click();
    await expect(input).toHaveValue("Swiss Confederation (ch-federal)");
  });

  test("the same picker on authority setup is equally reachable", async ({ page }) => {
    await mockPlatformControlApi(page);
    await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(BIG_REGISTRY),
      }),
    );

    await page.goto("/#/authorities/create");
    const picker = page.getByTestId("authority-jurisdiction-combobox");
    const input = picker.getByRole("combobox");
    await input.click();
    await input.fill("zurich");
    await expect(page.getByRole("option", { name: "Kanton Zürich (ch-zh)" })).toBeVisible();
  });
});
