/**
 * Desktop three-panel workspace: geometry, collapse, and detail selection.
 *
 * ## Before you believe a red result here, check which server you hit
 *
 * `playwright.config.ts` sets `reuseExistingServer: true` on port 3101. If
 * *anything* already holds 3101 — most often a `evidara-legal-search-frontend`
 * Docker container from `docker compose up` — Playwright attaches to it and
 * reports that build's behaviour under your branch's name. The container is not
 * rebuilt when you check out a branch, so it can be arbitrarily old.
 *
 * That is not hypothetical: it is exactly how #711 was filed. The two guards
 * below (`:69` handle geometry, `:85` filter-rail collapse) were reported as
 * failing on main, with `Expected: >= 16 / Received: 1`. Re-run against a
 * server whose identity was verified, both pass — the `Received: 1` came from a
 * container image built ~25h *before* #700 (the commit that fixes both) merged.
 * The guards are correct and the behaviour is fixed; only the server was wrong.
 *
 * So: a failure here that reports a 1px separator, or a filter rail that never
 * shows "Filterbereich einblenden", is a **stale-server symptom until proven
 * otherwise**. Confirm identity before opening an issue or marking anything
 * `test.fixme()` — a suppressed passing test is the dishonest signal ADR-0040
 * exists to prevent. `ss -ltnp | grep 3101` and `docker ps` are the fast check;
 * #719 makes the run assert this for you.
 */
import { expect, type Page, test } from "@playwright/test";
import { mockSearchApi } from "./helpers/mock-api";

// Use a wide viewport so the three-panel layout renders fully
test.use({ viewport: { width: 1600, height: 900 } });

test.describe("Workspace Panels", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearchApi(page);
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
  });

  // The UI renders in German (`de` is the default locale) and the mock builds
  // the result title from the query. These assertions had drifted to English
  // copy and an ISO date that the UI has not produced for some time, so the
  // whole spec was red before any of the fixes in this change.
  const RESULT_TITLE = "Result for Art. 754 OR Verantwortlichkeit";

  test("renders three resizable panels and two handles", async ({ page }) => {
    await expect(page.locator("[data-panel]")).toHaveCount(3);
    await expect(page.getByRole("separator")).toHaveCount(2);
    await expect(
      page.locator("[data-panel]").first().getByText("Filter", { exact: true }),
    ).toHaveCount(1);
  });

  test("loads deterministic result card content in center panel", async ({ page }) => {
    await expect(page.getByText(RESULT_TITLE)).toBeVisible();
    await expect(page.getByText("03.04.2026")).toBeVisible();
  });

  test("detail panel transitions from empty to selected item", async ({ page }) => {
    await expect(page.getByText("Kein Ergebnis ausgewählt")).toBeVisible();

    await page.getByText(RESULT_TITLE).click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(
      page.getByText("BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats"),
    ).toBeVisible();
  });

  // Regression guard for the react-resizable-panels v4 units bug: a bare-number
  // size is PIXELS in v4, so `minSize={25}` / `resize(32)` collapsed the filter
  // rail to ~28px and the detail panel to ~32px. The structural checks above
  // still pass at those widths (the panels exist and their text is in the DOM),
  // which is exactly why they missed it. Assert real rendered geometry instead.
  //
  // The reader is located by its testid rather than by panel index: since
  // #1053 an open document lays out five columns, and `nth(2)` is the outline
  // rail.
  test("filter rail and reader render at usable widths, not px slivers", async ({ page }) => {
    const panels = page.locator("[data-panel]");
    // Filter rail is ~18% of the 1600px row (≈288px); a pixel-collapsed rail is ~28px.
    const filterBox = await panels.nth(0).boundingBox();
    expect(filterBox?.width ?? 0).toBeGreaterThan(150);

    await page.getByText(RESULT_TITLE).click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(
      page.getByText("BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats"),
    ).toBeVisible();
    const detailBox = await page.getByTestId("detail-panel").boundingBox();
    expect(detailBox?.width ?? 0).toBeGreaterThan(300);
  });

  // Regression guard for #679: both separators measured exactly 1 physical
  // pixel wide, so the drag handle was practically unhittable with a mouse and
  // unreachable by touch — well under WCAG 2.5.5 (44px) and 2.5.8 (24px).
  // Geometry, not pixels: a 1px handle is invisible to screenshot diffing
  // (that is the #611 lesson), but a bounding box states it outright.
  test("resize handles expose a hittable target, not a 1px sliver", async ({ page }) => {
    const separators = page.getByRole("separator");
    await expect(separators).toHaveCount(2);

    for (const separator of await separators.all()) {
      const box = await separator.boundingBox();
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(16);
      // Full-height along the panel row — the target is a strip, not a dot.
      expect(box?.height ?? 0).toBeGreaterThan(200);
    }
  });

  // Regression guard for #610: dragging the rail below `minSize` collapsed it
  // to a sliver that rendered the *full* FilterPanel clipped into unreadable
  // fragments ("FILT", "S C", "A C"). Collapsed must render the icon rail with
  // an expand affordance instead — and expanding must restore a usable width.
  test("collapsing the filter rail renders an icon rail that can be expanded", async ({ page }) => {
    const filterPanel = page.locator("[data-panel]").first();
    const separator = page.getByRole("separator").first();

    const separatorBox = await separator.boundingBox();
    if (!separatorBox) throw new Error("filter rail separator has no bounding box");

    // Drag the handle far left, past `minSize`, so the rail collapses.
    await page.mouse.move(
      separatorBox.x + separatorBox.width / 2,
      separatorBox.y + separatorBox.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(0, separatorBox.y + separatorBox.height / 2, { steps: 10 });
    await page.mouse.up();

    const expandButton = filterPanel.getByRole("button", { name: /Filterbereich einblenden/ });
    await expect(expandButton).toBeVisible();
    // The clipped full panel must be gone, not merely narrow.
    await expect(filterPanel.getByText("Keine Filter verfügbar")).toHaveCount(0);

    const collapsedBox = await filterPanel.boundingBox();
    expect(collapsedBox?.width ?? 0).toBeLessThan(100);

    await expandButton.click();
    await expect(expandButton).toHaveCount(0);
    const expandedBox = await filterPanel.boundingBox();
    expect(expandedBox?.width ?? 0).toBeGreaterThan(150);
  });
});

/**
 * Reading mode (#1053) — the geometry jsdom cannot see.
 *
 * `src/__tests__/reading-layout.test.ts` asserts the RULE (which rail gives way
 * first, and what each column's share works out to). This file asserts what a
 * browser actually renders, which is the only place the rule and the stylesheet
 * are checked against each other: the panel row's width comes from
 * `--container-max` and `.shell-frame`'s gutters, and a model of those is not
 * them.
 *
 * The measure is MEASURED, not computed. `charactersPerLine` walks the rendered
 * text one character at a time, groups the characters by the line box they land
 * in, and returns the mean over full lines. That is what makes "51 characters"
 * and "inside the 65-75 band" the same kind of claim.
 */
test.describe("Reading mode", () => {
  /** Mean characters per full line of the given block's paragraphs. */
  async function charactersPerLine(page: Page, selector: string) {
    return page.evaluate((sel) => {
      const root = document.querySelector(sel);
      if (!root) throw new Error(`no element matches ${sel}`);

      let characters = 0;
      let lines = 0;
      for (const paragraph of Array.from(root.querySelectorAll("p"))) {
        const node = paragraph.firstChild;
        if (!node || node.nodeType !== Node.TEXT_NODE) continue;
        const text = node.textContent ?? "";
        if (text.length < 80) continue;

        // Group characters by the vertical position of their own rect. A
        // paragraph's line count alone would not do: dividing its characters
        // by its line count charges the short final line against the mean.
        const perLine = new Map<number, number>();
        const range = document.createRange();
        for (let i = 0; i < text.length; i++) {
          range.setStart(node, i);
          range.setEnd(node, i + 1);
          const rect = range.getBoundingClientRect();
          if (rect.width === 0 && rect.height === 0) continue;
          const key = Math.round(rect.top);
          perLine.set(key, (perLine.get(key) ?? 0) + 1);
        }

        const counts = Array.from(perLine.entries())
          .sort((a, b) => a[0] - b[0])
          .map(([, count]) => count);
        // Drop the last line of each paragraph: it stops where the paragraph
        // does, not where the column does.
        for (const count of counts.slice(0, -1)) {
          characters += count;
          lines += 1;
        }
      }

      return { characters, lines, mean: lines === 0 ? 0 : characters / lines };
    }, selector);
  }

  async function openReader(page: Page, width: number) {
    await mockSearchApi(page, { readerDetail: true });
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await page.locator("article").first().click();
    await expect(page).toHaveURL(/item=decision-1/);
    await expect(page.getByTestId("reader-body")).toBeVisible();
  }

  test("sets the reading column at 65-75 characters", async ({ page }) => {
    // The measurement #1053 opens with: 445px of panel, 403px of text and 51
    // characters per line, for a product whose job is reading law. The band is
    // the classic one — below ~65 the eye jumps lines too often, above ~75 it
    // loses the start of the next.
    await openReader(page, 1440);

    const measured = await charactersPerLine(page, '[data-testid="reader-body"]');
    // Printed so a CI log carries the number, not just a pass.
    console.log(
      `[#1053] 1440: ${measured.mean.toFixed(1)} characters/line over ${measured.lines} full lines`,
    );
    expect(measured.lines, "no wrapped lines were measured").toBeGreaterThan(8);
    expect(measured.mean).toBeGreaterThanOrEqual(65);
    expect(measured.mean).toBeLessThanOrEqual(75);
  });

  test("keeps the measure in band once the rails have collapsed", async ({ page }) => {
    // The collapse order exists to hold this. If the rails simply shrank
    // together, 1280 would squeeze the text instead of the reference material.
    await openReader(page, 1280);

    const measured = await charactersPerLine(page, '[data-testid="reader-body"]');
    console.log(
      `[#1053] 1280: ${measured.mean.toFixed(1)} characters/line over ${measured.lines} full lines`,
    );
    expect(measured.lines).toBeGreaterThan(8);
    expect(measured.mean).toBeGreaterThanOrEqual(65);
    expect(measured.mean).toBeLessThanOrEqual(75);
  });

  test("gives the reader more width than any other column", async ({ page }) => {
    await openReader(page, 1440);

    const reader = await page.getByTestId("detail-panel").boundingBox();
    expect(reader?.width ?? 0).toBeGreaterThanOrEqual(680);
    expect(reader?.width ?? 0).toBeLessThanOrEqual(760);

    const panels = page.locator("[data-panel]");
    await expect(panels).toHaveCount(5);
    for (const panel of await panels.all()) {
      const box = await panel.boundingBox();
      if (Math.abs((box?.x ?? 0) - (reader?.x ?? 0)) < 2) continue;
      expect(box?.width ?? 0).toBeLessThan(reader?.width ?? 0);
    }
  });

  test("collapses the filter rail while a document is open", async ({ page }) => {
    await openReader(page, 1440);

    const filterPanel = page.locator("[data-panel]").first();
    await expect(filterPanel.getByRole("button", { name: /Filterbereich einblenden/ })).toBeVisible();
    const box = await filterPanel.boundingBox();
    expect(box?.width ?? 0).toBeLessThan(100);
  });

  test("gives up the evidence rail before the outline", async ({ page }) => {
    // The stated order, measured. At 1280 the outline still lists sections and
    // the evidence rail is a strip; at 1100 both are strips and the outline
    // still states the position.
    await openReader(page, 1280);
    const outline = page.getByRole("navigation", { name: "Gliederung" });
    await expect(outline.getByRole("button", { name: /Meldepflicht/ })).toBeVisible();
    await expect(
      page.getByRole("complementary", { name: "Belege" }).getByRole("button", {
        name: /Belege einblenden/,
      }),
    ).toBeVisible();

    await page.setViewportSize({ width: 1100, height: 900 });
    await expect(outline.getByRole("button", { name: /Gliederung einblenden/ })).toBeVisible();
    // Collapsed, and still answering "where am I".
    await expect(page.getByTestId("reader-outline-position")).toBeVisible();
  });

  test("tracks the section the reader scrolls into", async ({ page }) => {
    // The scroll spy, against a rendered document — the case whose correct
    // answer does not come from `lib/reader-scroll-spy.ts`'s own derivation.
    await openReader(page, 1440);

    const outline = page.getByRole("navigation", { name: "Gliederung" });
    await expect(outline.getByRole("button", { name: /Allgemeine Bestimmungen/ })).toHaveAttribute(
      "aria-current",
      "location",
    );

    const scrollToSection = (sectionId: string) =>
      page.getByTestId("detail-scroll").evaluate((element, id) => {
        const heading = element.querySelector(`[data-section-id="${id}"]`) as HTMLElement;
        const top = heading.getBoundingClientRect().top - element.getBoundingClientRect().top;
        element.scrollTop += top - 8;
      }, sectionId);

    await scrollToSection("sec_3");
    await expect(outline.getByRole("button", { name: /Leinenpflicht/ })).toHaveAttribute(
      "aria-current",
      "location",
    );
    await expect(
      outline.getByRole("button", { name: /Allgemeine Bestimmungen/ }),
    ).not.toHaveAttribute("aria-current", "location");

    // And back: the rule is not one-way, and a spy that only ever advanced
    // would pass a forward-only test.
    await page.getByTestId("detail-scroll").evaluate((element) => {
      element.scrollTop = 0;
    });
    await expect(outline.getByRole("button", { name: /Allgemeine Bestimmungen/ })).toHaveAttribute(
      "aria-current",
      "location",
    );
  });

  test("moves the reader when a section is chosen from the rail", async ({ page }) => {
    await openReader(page, 1440);

    const outline = page.getByRole("navigation", { name: "Gliederung" });
    await outline.getByRole("button", { name: /Strafbestimmungen/ }).click();

    // The heading is at the top of the reader, and the URL still names the
    // document — never the section (`GET /v1/documents/sec_…` is #1040's 404).
    const offset = await page.getByTestId("detail-scroll").evaluate((element) => {
      const heading = element.querySelector('[data-section-id="sec_4"]') as HTMLElement;
      return Math.abs(heading.getBoundingClientRect().top - element.getBoundingClientRect().top);
    });
    expect(offset).toBeLessThan(80);
    await expect(page).toHaveURL(/item=decision-1/);
  });

  test("offers no jump for a section the body does not carry", async ({ page }) => {
    await openReader(page, 1440);

    const outline = page.getByRole("navigation", { name: "Gliederung" });
    await expect(outline.getByText("§ 10 Uebergangsrecht")).toBeVisible();
    await expect(outline.getByRole("button", { name: /Uebergangsrecht/ })).toHaveCount(0);
  });

  test("puts the evidence beside the text, and marks what the corpus lacks", async ({ page }) => {
    await openReader(page, 1440);

    const rail = page.getByRole("complementary", { name: "Belege" });
    await expect(rail.getByText("Einordnung")).toBeVisible();
    await expect(rail.getByRole("button", { name: /Tierschutzgesetz/ })).toBeVisible();
    // Unresolvable: not a link, and it says why.
    await expect(rail.getByRole("button", { name: /SR 210/ })).toHaveCount(0);
    await expect(rail.getByText("Die zitierte Norm ist nicht im Bestand.")).toBeVisible();
    // The text is still on screen while all of this is: that is the point.
    await expect(page.getByTestId("reader-body")).toBeVisible();
  });
});
