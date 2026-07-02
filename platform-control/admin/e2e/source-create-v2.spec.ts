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
const BLUEPRINT_TEMPLATES = {
  data: [
    { overlay_id: "ch", provider_template_id: "fedlex-default", provider: "fedlex_sparql" },
    { overlay_id: "at", provider_template_id: "ris-default", provider: "ris_ogd" },
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

  // Server-side blueprint preview.
  await page.route("**/api/platform-control/v1/sources/blueprint-preview*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BLUEPRINT_PREVIEW),
    }),
  );

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

test.describe("SourceCreateV2 wizard", () => {
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
    await page.goto("/#/sources-v2/create");
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
    await page.goto("/#/sources-v2/create");
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
    await page.goto("/#/sources-v2/create");
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

  test("blueprint preview raw-JSON toggle reveals the expanded acquisition_spec", async ({
    page,
  }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources-v2/create");
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
