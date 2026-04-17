/**
 * Badge Tokens — Unit Tests
 *
 * WHY THESE TESTS EXIST:
 * Badge colors are the visual identity of document types. The palette
 * is the contract between BFF and frontend: the BFF sends a colorKey,
 * the frontend renders colors from the palette.
 *
 * If a palette key produces a wrong color, or if the fallback breaks,
 * badges render as invisible or misleading — a quiet UX regression
 * that's easy to ship and hard to catch visually.
 *
 * This test is near-zero maintenance because the palette rarely changes.
 *
 * WHAT WE DON'T TEST:
 * - Which document types map to which colors (that's BFF logic)
 * - Badge rendering or styling (that's the Badge primitive)
 */

import { describe, expect, it } from "vitest";
import { getBadgeColor } from "@/lib/badge-tokens";

describe("getBadgeColor", () => {
  /**
   * WHY: Ensures each palette key returns distinct, correct values.
   * Catches accidental key renames or color swaps.
   */
  it("returns correct colors for each palette key", () => {
    expect(getBadgeColor("blue")).toEqual({ bg: "#dbeafe", text: "#1e40af" });
    // UX-7: `pink` was retuned from fuchsia (#fce7f3/#9d174d) to sky-blue so
    // court-decision badges no longer read as an error state next to the red
    // Swiss cross icon. Palette key kept for BFF backwards compatibility.
    expect(getBadgeColor("pink")).toEqual({ bg: "#e0f2fe", text: "#075985" });
    expect(getBadgeColor("indigo")).toEqual({ bg: "#e0e7ff", text: "#3730a3" });
    expect(getBadgeColor("green")).toEqual({ bg: "#d1fae5", text: "#065f46" });
  });

  /**
   * WHY: Unknown colorKeys must not crash or return undefined.
   * The BFF might send a key the frontend doesn't know about yet
   * (e.g., after adding a new document type). The fallback must
   * always produce a valid, visible badge.
   */
  it("returns fallback for unknown keys", () => {
    const fallback = getBadgeColor("unknown-type");
    expect(fallback.bg).toBeTruthy();
    expect(fallback.text).toBeTruthy();
  });

  it("returns fallback for undefined", () => {
    const fallback = getBadgeColor(undefined);
    expect(fallback.bg).toBeTruthy();
    expect(fallback.text).toBeTruthy();
  });

  it("returns fallback for empty string", () => {
    const fallback = getBadgeColor("");
    expect(fallback.bg).toBeTruthy();
    expect(fallback.text).toBeTruthy();
  });
});
