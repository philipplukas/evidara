import { expect, type Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixture data — mirrors the shapes the platform-control reference-data API
// returns. `getOne` for authorities/jurisdictions resolves by scanning the
// list endpoint (see dataProvider.findInSimpleList), so the edit tests only
// need the list mocks below — no per-id route required.
// ---------------------------------------------------------------------------

const JURISDICTIONS = {
  data: [
    {
      jurisdiction_id: "jur_ch",
      name: "Switzerland",
      slug: "ch",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      jurisdiction_id: "jur_at",
      name: "Austria",
      slug: "at",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

const AUTHORITIES = {
  data: [
    {
      authority_id: "auth_bger",
      jurisdiction_id: "jur_ch",
      name: "Bundesgericht",
      slug: "bger",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

// ---------------------------------------------------------------------------
// API mock setup — intercepts the reference-data endpoints and captures the
// write payloads so tests can assert the dataProvider serialised the form
// values correctly.
// ---------------------------------------------------------------------------

type Captured = { method: string; body: Record<string, unknown> | null };

async function mockReferenceApi(page: Page) {
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

  const captured: { authority: Captured | null; jurisdiction: Captured | null } = {
    authority: null,
    jurisdiction: null,
  };

  await page.route("**/api/platform-control/v1/reference-data/jurisdictions*", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(JURISDICTIONS),
      });
    }
    captured.jurisdiction = {
      method,
      body: JSON.parse(route.request().postData() ?? "null"),
    };
    return route.fulfill({
      status: method === "POST" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify({
        jurisdiction_id: "jur_new",
        name: "Germany",
        slug: "de",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    });
  });

  await page.route("**/api/platform-control/v1/reference-data/authorities*", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(AUTHORITIES),
      });
    }
    captured.authority = {
      method,
      body: JSON.parse(route.request().postData() ?? "null"),
    };
    return route.fulfill({
      status: method === "POST" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify({
        authority_id: "auth_new",
        jurisdiction_id: "jur_ch",
        name: "Bundesverwaltungsgericht",
        slug: "bvger",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    });
  });

  return captured;
}

/** Open a radix Select by its label, pick an option by visible text. */
async function pickRadixSelect(page: Page, label: string, optionText: string) {
  const trigger = page.getByRole("combobox", { name: label }).first();
  await expect(trigger).toBeVisible();
  await trigger.click();
  await page.getByRole("option", { name: optionText }).click();
}

test.describe("Reference-data admin forms (ADR-0026 collapse)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("evidara_user_role", "admin");
    });
  });

  test("authority create: parent picker, scope alert, submit payload", async ({ page }) => {
    const captured = await mockReferenceApi(page);

    await page.goto("/#/authorities/create");
    await expect(page.locator("h1")).toContainText("Create authority");

    // The scope alert defaults to the global-fallback warning (jurisdiction_id
    // starts null via CREATE_DEFAULTS). Exact match to avoid colliding with the
    // header copy, which also contains the phrase "a global authority".
    await expect(page.getByText("Global authority", { exact: true })).toBeVisible();

    // Parent picker is populated from the live jurisdictions list.
    const jurisdictionTrigger = page.getByRole("combobox", { name: "Jurisdiction" }).first();
    await jurisdictionTrigger.click();
    await expect(page.getByRole("option", { name: "Switzerland (ch)" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Austria (at)" })).toBeVisible();
    await page.getByRole("option", { name: "Switzerland (ch)" }).click();

    // Scoping to a jurisdiction flips the alert to the info variant.
    await expect(page.getByText("Scoped authority", { exact: true })).toBeVisible();
    await expect(page.getByText("Global authority", { exact: true })).toBeHidden();

    await page.getByLabel("Name").fill("Bundesverwaltungsgericht");
    await page.getByLabel("Slug").fill("bvger");
    await page.getByRole("button", { name: "Create authority" }).click();

    await expect.poll(() => captured.authority, { timeout: 5000 }).toBeTruthy();
    expect(captured.authority?.method).toBe("POST");
    expect(captured.authority?.body).toMatchObject({
      name: "Bundesverwaltungsgericht",
      slug: "bvger",
      jurisdiction_id: "jur_ch",
    });
  });

  test("authority edit: seeded values, slug + scope change alerts", async ({ page }) => {
    await mockReferenceApi(page);

    await page.goto("/#/authorities/auth_bger");
    await expect(page.locator("h1")).toContainText("Edit Bundesgericht");

    // Immutable id rendered disabled; no change alerts until the operator diverges.
    await expect(page.getByLabel("Authority ID")).toHaveValue("auth_bger");
    await expect(page.getByText("Authority slug changed")).toBeHidden();
    await expect(page.getByText("Authority scope changed")).toBeHidden();

    // Diverging the slug from the persisted "bger" raises the stability warning.
    await page.getByLabel("Slug").fill("bger-neu");
    await expect(page.getByText("Authority slug changed")).toBeVisible();

    // Moving from jur_ch to another jurisdiction raises the scope warning.
    await pickRadixSelect(page, "Jurisdiction", "Austria (at)");
    await expect(page.getByText("Authority scope changed")).toBeVisible();
  });

  test("jurisdiction create: submit payload", async ({ page }) => {
    const captured = await mockReferenceApi(page);

    await page.goto("/#/jurisdictions/create");
    await expect(page.locator("h1")).toContainText("Create jurisdiction");

    await page.getByLabel("Name").fill("Germany");
    await page.getByLabel("Slug").fill("de");
    await page.getByRole("button", { name: "Create jurisdiction" }).click();

    await expect.poll(() => captured.jurisdiction, { timeout: 5000 }).toBeTruthy();
    expect(captured.jurisdiction?.method).toBe("POST");
    expect(captured.jurisdiction?.body).toMatchObject({ name: "Germany", slug: "de" });
  });

  test("jurisdiction edit: seeded values + slug change alert", async ({ page }) => {
    await mockReferenceApi(page);

    await page.goto("/#/jurisdictions/jur_ch");
    await expect(page.locator("h1")).toContainText("Edit Switzerland");

    await expect(page.getByLabel("Jurisdiction ID")).toHaveValue("jur_ch");
    await expect(page.getByText("Jurisdiction slug changed")).toBeHidden();

    await page.getByLabel("Slug").fill("ch-neu");
    await expect(page.getByText("Jurisdiction slug changed")).toBeVisible();
  });
});
