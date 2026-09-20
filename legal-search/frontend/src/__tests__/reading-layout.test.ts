/**
 * The reading-mode collapse rule (#1053).
 *
 * The issue asks for the collapse ORDER to be decided rather than fall out of
 * a media query, so these are the assertions that fail when it is not:
 *
 *   - Invert the two thresholds in `lib/reading-layout.ts` and
 *     "gives up the evidence rail before the outline, at every desktop width"
 *     goes red.
 *   - Delete either threshold (make `readingRailStateFor` return `"full"`
 *     always) and "collapses the evidence rail at 1280" goes red.
 *   - Widen the reading-mode filter share back to the search layout's 18% and
 *     "keeps the filter rail collapsed at every desktop width" goes red.
 *   - Change one number in a `READING_SPLIT` row without changing another and
 *     "every split totals exactly 100" goes red — the renormalization trap
 *     documented on `DESKTOP_PANEL_SPLIT`.
 *
 * What these do NOT prove: that the rendered page matches the arithmetic. The
 * px helpers restate values CSS owns. `e2e/workspace-panels.spec.ts` measures
 * the same widths in a browser, which is the independent check.
 */
import { describe, expect, it } from "vitest";
import {
  FILTER_RAIL_COLLAPSED_THRESHOLD_PX,
  READING_RAIL_COLLAPSED_THRESHOLD_PX,
} from "@/app/WorkspaceClient";
import {
  EVIDENCE_RAIL_MIN_VIEWPORT_PX,
  isEvidenceRailCollapsed,
  isOutlineRailCollapsed,
  OUTLINE_RAIL_MIN_VIEWPORT_PX,
  READING_SPLIT,
  readingColumnPx,
  readingRailStateFor,
} from "@/lib/reading-layout";

/** Desktop starts at 1024 (`use-desktop.ts`); above 1600 the container caps. */
const DESKTOP_WIDTHS = Array.from({ length: (1700 - 1024) / 4 + 1 }, (_, i) => 1024 + i * 4);

describe("reading-mode split", () => {
  it("every split totals exactly 100", () => {
    for (const [state, split] of Object.entries(READING_SPLIT)) {
      const total = split.filters + split.results + split.outline + split.reader + split.evidence;
      expect(total, `${state} totals ${total}`).toBe(100);
    }
  });

  it("never gives the reader less room as rails collapse", () => {
    expect(READING_SPLIT.evidenceCollapsed.reader).toBeGreaterThan(READING_SPLIT.full.reader);
    expect(READING_SPLIT.outlineCollapsed.reader).toBeGreaterThan(
      READING_SPLIT.evidenceCollapsed.reader,
    );
  });

  it("keeps the result strip — reading mode narrows it, it does not retire it", () => {
    // Dropping the list entirely is #1040's, after a back control and a
    // "next hit" affordance exist. Every state still allocates it width.
    for (const [state, split] of Object.entries(READING_SPLIT)) {
      expect(split.results, `${state} has no result strip`).toBeGreaterThan(0);
    }
  });
});

describe("collapse order", () => {
  it("collapses the evidence rail at 1280 and keeps the outline listed", () => {
    const state = readingRailStateFor(1280);
    expect(isEvidenceRailCollapsed(state)).toBe(true);
    expect(isOutlineRailCollapsed(state)).toBe(false);
  });

  it("lists both rails at the 1440 design width", () => {
    const state = readingRailStateFor(1440);
    expect(isEvidenceRailCollapsed(state)).toBe(false);
    expect(isOutlineRailCollapsed(state)).toBe(false);
  });

  it("collapses the outline only once the evidence rail already is", () => {
    const state = readingRailStateFor(1100);
    expect(isOutlineRailCollapsed(state)).toBe(true);
    expect(isEvidenceRailCollapsed(state)).toBe(true);
  });

  it("gives up the evidence rail before the outline, at every desktop width", () => {
    // The order IS the decision. Swap the two thresholds and this is the
    // assertion that names it: there must be no width where the outline is a
    // strip while the evidence rail is still listed.
    const offenders = DESKTOP_WIDTHS.filter((width) => {
      const state = readingRailStateFor(width);
      return isOutlineRailCollapsed(state) && !isEvidenceRailCollapsed(state);
    });
    expect(offenders).toEqual([]);
    expect(OUTLINE_RAIL_MIN_VIEWPORT_PX).toBeLessThan(EVIDENCE_RAIL_MIN_VIEWPORT_PX);
  });

  it("never collapses the reader itself", () => {
    for (const width of DESKTOP_WIDTHS) {
      expect(readingColumnPx(width, "reader"), `reader at ${width}`).toBeGreaterThan(
        READING_RAIL_COLLAPSED_THRESHOLD_PX * 4,
      );
    }
  });
});

describe("rendered widths the rule produces", () => {
  it("keeps the filter rail collapsed at every desktop width", () => {
    // "Filters collapse while a document is open" is delivered by the share
    // they get, not by a separate flag: `WorkspaceClient` derives the icon
    // rail from the rendered px.
    for (const width of DESKTOP_WIDTHS) {
      expect(readingColumnPx(width, "filters"), `filters at ${width}`).toBeLessThan(
        FILTER_RAIL_COLLAPSED_THRESHOLD_PX,
      );
    }
  });

  it("renders a collapsed rail as a strip and a listed rail as a list", () => {
    for (const width of DESKTOP_WIDTHS) {
      const state = readingRailStateFor(width);

      const evidence = readingColumnPx(width, "evidence");
      if (isEvidenceRailCollapsed(state)) {
        expect(evidence, `evidence at ${width}`).toBeLessThan(READING_RAIL_COLLAPSED_THRESHOLD_PX);
      } else {
        expect(evidence, `evidence at ${width}`).toBeGreaterThan(
          READING_RAIL_COLLAPSED_THRESHOLD_PX,
        );
      }

      const outline = readingColumnPx(width, "outline");
      if (isOutlineRailCollapsed(state)) {
        expect(outline, `outline at ${width}`).toBeLessThan(READING_RAIL_COLLAPSED_THRESHOLD_PX);
      } else {
        expect(outline, `outline at ${width}`).toBeGreaterThan(READING_RAIL_COLLAPSED_THRESHOLD_PX);
      }
    }
  });

  it("gives the reader the width #1053 asks for at 1440", () => {
    // ~680-760px is the band the issue states for a 65-75 character measure.
    // The character count itself is measured in a browser, not modelled here.
    const reader = readingColumnPx(1440, "reader");
    expect(reader).toBeGreaterThanOrEqual(680);
    expect(reader).toBeLessThanOrEqual(760);
  });

  it("does not let a narrow window starve the reader", () => {
    // The collapse order exists to hold this: at 1024 the reader is still
    // wider than it was at 1440 before reading mode (445px panel).
    for (const width of DESKTOP_WIDTHS) {
      expect(readingColumnPx(width, "reader"), `reader at ${width}`).toBeGreaterThan(600);
    }
  });
});
