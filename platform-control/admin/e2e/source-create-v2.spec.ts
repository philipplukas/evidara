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

const CREATED_SOURCE = {
  source_id: "src_test_001",
  name: "Swiss Federal Codes",
  description: "Test source",
  jurisdiction_id: "jur_ch",
  authority_id: "auth_fedlex",
  source_type: "website",
  document_family: null,
  enabled: true,
  created_at: "2026-04-22T00:00:00Z",
  updated_at: "2026-04-22T00:00:00Z",
};

// ---------------------------------------------------------------------------
// API mock setup — intercepts /api/platform-control/* at the browser level
// ---------------------------------------------------------------------------

async function mockPlatformControlApi(page: Page) {
  /** Captured create-source payload for assertions. */
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

  // Sources endpoint: create, list, and post-create redirect fetches.
  await page.route("**/api/platform-control/v1/sources*", async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() === "POST") {
      capturedCreatePayload = JSON.parse(request.postData() ?? "{}");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(CREATED_SOURCE),
      });
      return;
    }
    // Individual source fetch (show page after redirect)
    if (url.includes("/sources/src_test_001")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CREATED_SOURCE),
      });
    }
    // Sources list
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [CREATED_SOURCE] }),
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

  test("full source setup flow: fill form and submit source payload", async ({ page }) => {
    const mocks = await mockPlatformControlApi(page);

    // Navigate to the Tailwind + ra-core create page.
    // react-admin uses hash routing by default
    await page.goto("/#/sources-v2/create");

    // Wait for the page heading
    await expect(page.locator("h1")).toContainText("Create source");

    // ── Fill source metadata ──
    await page.getByLabel("Name").fill("Swiss Federal Codes");
    await page.getByLabel("Description").fill("Test source for e2e");
    await page.getByLabel("Source type").fill("website");

    // Pick jurisdiction: Switzerland (ch)
    await pickRadixSelect(page, "Jurisdiction", "Switzerland (ch)");

    // After picking Switzerland, authority should filter — pick Fedlex
    await pickRadixSelect(page, "Authority", "Fedlex (fedlex)");

    // ── Submit the form ──
    await page.getByRole("button", { name: "Create source" }).click();

    // Verify the payload sent to the API
    await expect.poll(() => mocks.getCapturedPayload(), { timeout: 5000 }).toBeTruthy();

    const payload = mocks.getCapturedPayload()!;
    expect(payload).toMatchObject({
      name: "Swiss Federal Codes",
      description: "Test source for e2e",
      jurisdiction_id: "jur_ch",
      authority_id: "auth_fedlex",
      source_type: "website",
    });
  });

  test("authority select filters when jurisdiction changes", async ({ page }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources-v2/create");
    await expect(page.locator("h1")).toContainText("Create source");

    // Pick Switzerland — should show Fedlex + Global Authority
    await pickRadixSelect(page, "Jurisdiction", "Switzerland (ch)");

    // Open authority dropdown and check visible options
    const authorityTrigger = page.getByRole("combobox", { name: "Authority" }).first();
    await authorityTrigger.click();

    await expect(page.getByRole("option", { name: "Fedlex (fedlex)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Global Authority (global)" })).toBeVisible();
    // RIS (Austrian) should NOT be visible
    await expect(page.getByRole("option", { name: "RIS (ris)" })).toBeHidden();

    // Close by pressing Escape
    await page.keyboard.press("Escape");

    // Switch to Austria — should show RIS + Global Authority
    await pickRadixSelect(page, "Jurisdiction", "Austria (at)");

    // Open authority again (remounted due to key change)
    const authorityTrigger2 = page.getByRole("combobox", { name: "Authority" }).first();
    await authorityTrigger2.click();

    await expect(page.getByRole("option", { name: "RIS (ris)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Global Authority (global)" })).toBeVisible();
    // Fedlex (Swiss) should NOT be visible
    await expect(page.getByRole("option", { name: "Fedlex (fedlex)" })).toBeHidden();
  });

  test("shows the operator provider-setup note", async ({ page }) => {
    await mockPlatformControlApi(page);
    await page.goto("/#/sources-v2/create");
    await expect(page.locator("h1")).toContainText("Create source");

    const notice = page.locator("aside");
    await expect(notice.getByText("Operator note")).toBeVisible();
    await expect(
      notice.getByText(
        "Use the acquisition configuration fields after creation to complete provider setup.",
      ),
    ).toBeVisible();
  });
});
