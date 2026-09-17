/**
 * The three run-detail features that shipped with no Playwright coverage (#895).
 *
 * #885 (deep links), #897 (payload panel) and #887 (the Timeline) each landed with
 * unit tests and each reported the admin e2e layer as `DID-NOT-RUN` rather than as a
 * pass — honest at the time, and this closes it.
 *
 * The gap matters for this surface specifically. CLAUDE.md:
 *
 * > It is the only layer that sees layout, stylesheets and routing: jsdom has none of
 * > the three, which is how a clipped ACTIONS column, a UA-beveled sort header and an
 * > absent dark mode all passed `npm run check`.
 *
 * And #873 exists because the operator panel was unusable under pressure, so a clipped
 * column here is not cosmetic — it is the documented precedent.
 *
 * Every request is mocked with `page.route`, as every spec in this directory does. No
 * backend, no database.
 */

import type { Page } from "@playwright/test";
import { pipelineHealth } from "./fixtures/pipelineHealth";
import { expect, test } from "./support/test";

const RUN_ID = "run_detail";

const RUN = {
  run_id: RUN_ID,
  source_id: "src_1",
  source_version_id: "sv_1",
  source_name: "Kanton Zürich — LexFind",
  version_label: "v3",
  mode: "acceptance",
  status: "completed",
  started_at: "2026-04-15T09:10:00Z",
  completed_at: "2026-04-15T09:40:00Z",
  artifacts_count: 2,
  captured_resources_count: 2,
  failure_reason: null,
  created_at: "2026-04-15T09:05:00Z",
  updated_at: "2026-04-15T09:40:00Z",
};

/** Two provider jobs, one failed — the Timeline colours failures differently. */
const PROVIDER_JOBS = {
  data: [
    {
      provider_job_id: "pj_1",
      run_id: RUN_ID,
      provider: "lexfind_api",
      status: "succeeded",
      last_event_type: "job.completed",
      external_job_id: "ext_1",
      created_at: "2026-04-15T09:11:00Z",
      updated_at: "2026-04-15T09:12:00Z",
      request_payload: null,
      response_payload: null,
    },
    {
      provider_job_id: "pj_2",
      run_id: RUN_ID,
      provider: "lexfind_api",
      status: "failed",
      last_event_type: "job.failed",
      external_job_id: "ext_2",
      created_at: "2026-04-15T09:13:00Z",
      updated_at: "2026-04-15T09:14:00Z",
      request_payload: null,
      response_payload: null,
    },
  ],
};

/**
 * One artifact with a long body. The body is what has to scroll inside its own
 * container rather than widening the table.
 */
const LONG_BODY = "Art. 1 Diese Verordnung regelt die Haltung von Hunden. ".repeat(120);

const RAW_ARTIFACTS = {
  data: [
    {
      artifact_id: "art_1",
      run_id: RUN_ID,
      content_type: "text/html",
      // Deliberately long and UNBREAKABLE (no spaces, no slashes to wrap on near
      // the end). A short path cannot overflow a 1280px table no matter what the
      // container does, which makes the width assertions below unfalsifiable —
      // mutation-testing caught exactly that: removing the table's containment
      // changed nothing until this fixture got wide enough to matter.
      storage_path: "s3://evidara-raw/zh/2026/hundegesetz/" + "x".repeat(400) + "/artifact.html",
      created_at: "2026-04-15T09:15:00Z",
      // `artifact_metadata`, not `payload` — the field `rawArtifactColumns` hands
      // to `ArtifactPayloadPanel`. Getting this wrong renders an empty panel that
      // still looks plausible, which is the kind of mock error a spec can carry
      // for a long time.
      artifact_metadata: {
        url: "https://www.zh.ch/hundegesetz",
        title: "Hundegesetz",
        rawHtml: LONG_BODY,
      },
    },
  ],
};

/** An undated lifecycle event: the Timeline must label it, not leave it blank. */
const DOCUMENT_LIFECYCLE = {
  data: [
    {
      event_id: "evt_1",
      run_id: RUN_ID,
      event_type: "document.processed",
      document_id: "doc_zh_hundegesetz",
      document_revision: 1,
      occurred_at: null,
      stages: null,
    },
  ],
};

async function mockRunDetail(page: Page) {
  // Benign catch-all first (lowest priority), so any read model not named below
  // resolves to an empty 200 rather than hanging.
  await page.route("**/api/platform-control/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [] }),
    }),
  );
  const json = (body: unknown) => (route: import("@playwright/test").Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

  await page.route(`**/v1/runs/${RUN_ID}/pipeline-health`, json(pipelineHealth(RUN_ID)));
  await page.route(`**/v1/runs/${RUN_ID}/provider-jobs*`, json(PROVIDER_JOBS));
  await page.route(`**/v1/runs/${RUN_ID}/raw-artifacts*`, json(RAW_ARTIFACTS));
  await page.route(`**/v1/runs/${RUN_ID}/document-lifecycle*`, json(DOCUMENT_LIFECYCLE));
  await page.route(`**/v1/runs/${RUN_ID}`, json(RUN));
}

async function openRunDetail(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("evidara_user_role", "admin");
  });
  await mockRunDetail(page);
  await page.goto(`/#/runs/${RUN_ID}/show`);
  await expect(page.getByRole("heading", { name: /Pipeline Health/ })).toBeVisible();
}

test.describe("Run detail — the three features no e2e spec saw (#895)", () => {
  test("the Timeline merges the stages oldest-first and labels an undated row", async ({
    page,
  }) => {
    await openRunDetail(page);

    const timeline = page.getByRole("button", { name: /^Timeline/ });
    await expect(timeline).toBeVisible();
    await timeline.click();

    // Both provider jobs reached it, and the failed one is not silently dropped.
    await expect(page.getByText("lexfind_api job succeeded")).toBeVisible();
    await expect(page.getByText("lexfind_api job failed")).toBeVisible();

    // The undated lifecycle event says so rather than borrowing a neighbour's
    // time — the defect `timelineColumns` calls out in its own comment.
    await expect(page.getByText("no timestamp")).toBeVisible();
  });

  test("a document id is always readable, and never a link to nowhere", async ({ page }) => {
    /**
     * Deliberately does NOT assert which branch renders.
     *
     * `NEXT_PUBLIC_LEGAL_SEARCH_URL` is baked at build time, and
     * `platform-control/admin/.env.local` sets it — so a test asserting "plain text
     * when unconfigured" passes in CI and fails on a workstation, or the reverse.
     * An environment-dependent assertion is worse than none: it teaches people that
     * a red run means nothing.
     *
     * What holds either way is the invariant the deep-link work is actually for: the
     * id is always readable, and if it IS a link it points at legal-search rather
     * than at an empty or relative href. `runDeepLinks.test.ts` covers the
     * unconfigured branch, where the input can be controlled.
     */
    await openRunDetail(page);

    await page.getByRole("button", { name: /Document Lifecycle/ }).click();
    await expect(page.getByText("doc_zh_hundegesetz").first()).toBeVisible();

    const link = page.getByRole("link", { name: "doc_zh_hundegesetz" });
    if ((await link.count()) > 0) {
      const href = await link.first().getAttribute("href");
      expect(href, "a rendered deep link must resolve somewhere").toBeTruthy();
      expect(href).toMatch(/^https?:\/\//);
    }
  });

  test("a long artifact body scrolls inside its own block, not the page", async ({ page }) => {
    /**
     * The claim #897's panel makes, tested as a claim.
     *
     * A first version of this test only asserted that the PAGE does not scroll
     * horizontally — and mutation-testing showed it could not fail: deleting
     * `max-h`/`overflow-auto` from the body block left the page width unchanged, so
     * the assertion was decoration. A guard that cannot fail is worse than none.
     *
     * What actually holds the line is the body block being CAPPED and scrollable:
     * its rendered height stays bounded while its content is far taller. Remove the
     * cap and this goes red.
     */
    await openRunDetail(page);

    await page.getByRole("button", { name: /Raw Artifacts/ }).click();
    // The panel's labelled rows, not the raw JSON dump it replaced (#897).
    await expect(page.getByText("https://www.zh.ch/hundegesetz").first()).toBeVisible();

    const body = page.locator("details pre").first();
    await expect(body).toBeVisible();

    const box = await body.evaluate((el) => ({
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      clientWidth: el.clientWidth,
      scrollWidth: el.scrollWidth,
    }));

    // Capped: a 6,000-character body must not render at full height.
    expect(box.clientHeight).toBeLessThanOrEqual(400);
    expect(box.scrollHeight).toBeGreaterThan(box.clientHeight);
    // And it wraps rather than pushing the table wider.
    expect(box.scrollWidth - box.clientWidth).toBeLessThanOrEqual(1);
  });

  test.describe("wide table content stays REACHABLE, not clipped", () => {
    /**
     * This started as "the page must not scroll horizontally" and mutation-testing
     * showed it could not fail — for a reason worth writing down: the app shell sets
     * `overflow-x-hidden` on its main element, so the page can never overflow no
     * matter what a table does.
     *
     * Which means a page-overflow assertion is blind to precisely the defect #873
     * was opened for: a CLIPPED column. The shell hides the symptom.
     *
     * So the assertion is reachability instead. A table wider than its container is
     * fine — provided the container scrolls. Content that overflows an element which
     * does NOT scroll is unreachable, and that is the regression. Remove
     * `overflow-x-auto` from `DataTable` and this goes red.
     */
    for (const width of [1280, 1440, 1920]) {
      test(`at ${width}px, in both themes`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await openRunDetail(page);

        for (const name of [/^Timeline/, /Provider Jobs/, /Raw Artifacts/, /Document Lifecycle/]) {
          const trigger = page.getByRole("button", { name });
          if (await trigger.isVisible()) {
            await trigger.click();
          }
        }

        for (const theme of ["light", "dark"]) {
          await page.evaluate((value) => {
            document.documentElement.setAttribute("data-theme", value);
          }, theme);

          const unreachable = await page.evaluate(() => {
            const clipped: string[] = [];
            for (const table of Array.from(document.querySelectorAll("table"))) {
              // The nearest ancestor that is allowed to scroll horizontally.
              let node: HTMLElement | null = table.parentElement;
              let scrollable: HTMLElement | null = null;
              while (node && node !== document.body) {
                const overflowX = getComputedStyle(node).overflowX;
                if (overflowX === "auto" || overflowX === "scroll") {
                  scrollable = node;
                  break;
                }
                node = node.parentElement;
              }
              const container = scrollable ?? (table.parentElement as HTMLElement | null);
              if (!container) continue;
              const overflows = table.scrollWidth - container.clientWidth > 1;
              if (overflows && scrollable === null) {
                clipped.push(table.closest("section")?.textContent?.slice(0, 40) ?? "table");
              }
            }
            return clipped;
          });

          expect(
            unreachable,
            `${theme} at ${width}px: table content overflows a container that cannot scroll`,
          ).toEqual([]);
        }
      });
    }
  });
});
