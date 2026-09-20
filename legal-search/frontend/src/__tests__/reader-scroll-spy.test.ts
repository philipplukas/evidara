/**
 * The reading position rule (#1053).
 *
 * Delete `activeSectionAt`'s loop (return `offsets[0].id` always) and
 * "moves to the section the reader has scrolled into" goes red. Invert the
 * comparison (`offset.top < readingLine` → `>`) and both that test and
 * "reports the last heading at or above the reading line" go red. Drop
 * `READING_LINE_OFFSET_PX` to 0 and "counts a heading just below the top edge
 * as the one being read" goes red.
 *
 * The fixture is a real outline shape: the ZH Hundegesetz's own sections, with
 * the offsets a scrolled body produces. Whether the RULE is right for a
 * rendered document is settled elsewhere and independently — the Playwright
 * test scrolls the real reader and reads the rail's `aria-current`.
 */
import { describe, expect, it } from "vitest";
import {
  activeSectionAt,
  READING_LINE_OFFSET_PX,
  type SectionOffset,
} from "@/lib/reader-scroll-spy";

const OFFSETS: SectionOffset[] = [
  { id: "sec_1", top: 0 },
  { id: "sec_2", top: 600 },
  { id: "sec_3", top: 1400 },
  { id: "sec_4", top: 2600 },
];

describe("activeSectionAt", () => {
  it("reports nothing when the document placed no heading", () => {
    // `null` is a real answer, not "the first one": `buildDocumentOutline`
    // reports sections it could not place, and marking one of those would
    // claim a position the reader is not at.
    expect(activeSectionAt([], 0)).toBeNull();
    expect(activeSectionAt([], 4000)).toBeNull();
  });

  it("reports the first section while the reader is above every heading", () => {
    expect(activeSectionAt([{ id: "sec_1", top: 900 }], 0)).toBe("sec_1");
  });

  it("moves to the section the reader has scrolled into", () => {
    expect(activeSectionAt(OFFSETS, 0)).toBe("sec_1");
    expect(activeSectionAt(OFFSETS, 700)).toBe("sec_2");
    expect(activeSectionAt(OFFSETS, 1500)).toBe("sec_3");
    expect(activeSectionAt(OFFSETS, 9000)).toBe("sec_4");
  });

  it("reports the last heading at or above the reading line, not the next one", () => {
    // One pixel before sec_3's heading reaches the reading line the reader is
    // still finishing sec_2. Highlighting sec_3 there marks a section whose
    // first line is not on screen.
    expect(activeSectionAt(OFFSETS, 1400 - READING_LINE_OFFSET_PX - 1)).toBe("sec_2");
    expect(activeSectionAt(OFFSETS, 1400 - READING_LINE_OFFSET_PX)).toBe("sec_3");
  });

  it("counts a heading just below the top edge as the one being read", () => {
    // Without the reading-line offset, a heading sitting a few pixels under
    // the top of the viewport is "below" and the rail lags a whole section.
    const scrollTop = 600 - READING_LINE_OFFSET_PX + 8;
    expect(activeSectionAt(OFFSETS, scrollTop)).toBe("sec_2");
  });

  it("follows document order rather than proximity", () => {
    // A later section whose heading is still far below must not win because
    // its distance happens to be smaller in absolute terms.
    const unevenly: SectionOffset[] = [
      { id: "sec_a", top: 0 },
      { id: "sec_b", top: 4000 },
    ];
    expect(activeSectionAt(unevenly, 3800)).toBe("sec_a");
  });
});
