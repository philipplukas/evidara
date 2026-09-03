import { describe, expect, it } from "vitest";
import {
  NO_TABLE_OVERFLOW,
  resolveTableOverflow,
  sameTableOverflow,
  tableOverflowState,
} from "./tableOverflow";

describe("resolveTableOverflow", () => {
  it("reports nothing to scroll when the table fits", () => {
    expect(resolveTableOverflow({ scrollLeft: 0, scrollWidth: 800, clientWidth: 800 })).toEqual(
      NO_TABLE_OVERFLOW,
    );
  });

  it("reports content to the right — the run queue at 1440px", () => {
    // The measurement from the running app: scrollWidth 1160 > clientWidth
    // 1054, with UPDATED and ACTIONS past the edge and no cue of any kind.
    const overflow = resolveTableOverflow({
      scrollLeft: 0,
      scrollWidth: 1160,
      clientWidth: 1054,
    });
    expect(overflow).toEqual({ overflowing: true, canScrollLeft: false, canScrollRight: true });
    expect(tableOverflowState(overflow)).toBe("right");
  });

  it("reports both edges mid-scroll and only the left edge at the end", () => {
    expect(
      tableOverflowState(
        resolveTableOverflow({ scrollLeft: 50, scrollWidth: 1160, clientWidth: 1054 }),
      ),
    ).toBe("both");
    expect(
      tableOverflowState(
        resolveTableOverflow({ scrollLeft: 106, scrollWidth: 1160, clientWidth: 1054 }),
      ),
    ).toBe("left");
  });

  it("tolerates sub-pixel widths rather than flickering a cue on a table that fits", () => {
    // Fractional layout and browser zoom routinely report scrollWidth a
    // fraction over clientWidth for a table that does not scroll.
    expect(
      resolveTableOverflow({ scrollLeft: 0, scrollWidth: 800.5, clientWidth: 800 }).overflowing,
    ).toBe(false);
  });
});

describe("sameTableOverflow", () => {
  it("compares by value, because the component re-measures after every render", () => {
    const a = resolveTableOverflow({ scrollLeft: 0, scrollWidth: 1160, clientWidth: 1054 });
    const b = resolveTableOverflow({ scrollLeft: 0, scrollWidth: 1160, clientWidth: 1054 });
    // Different objects. Without value equality the state update would never
    // settle and the render-time measurement would loop.
    expect(a).not.toBe(b);
    expect(sameTableOverflow(a, b)).toBe(true);
  });

  it("sees a real change", () => {
    const before = resolveTableOverflow({ scrollLeft: 0, scrollWidth: 1160, clientWidth: 1054 });
    const after = resolveTableOverflow({ scrollLeft: 60, scrollWidth: 1160, clientWidth: 1054 });
    expect(sameTableOverflow(before, after)).toBe(false);
  });
});
