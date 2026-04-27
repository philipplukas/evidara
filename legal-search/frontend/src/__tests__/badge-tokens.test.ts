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
 * Values resolve via CSS custom properties defined in `styles/tokens/tokens.css`
 * so we assert the token reference rather than a concrete color. This keeps
 * dark-mode overrides and cross-app consistency free.
 *
 * WHAT WE DON'T TEST:
 * - Which document types map to which colors (that's BFF logic)
 * - Badge rendering or styling (that's the Badge primitive)
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getBadgeColor } from "@/lib/badge-tokens";

const sharedTokenCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");

describe("getBadgeColor", () => {
  /**
   * WHY: Ensures each palette key returns distinct, correct tokens.
   * Catches accidental key renames or color swaps.
   */
  it("returns correct token references for each palette key", () => {
    // The `pink` slot was retuned from fuchsia to sky-blue (UX-7) so
    // court-decision badges no longer read as an error state next to the red
    // Swiss cross icon. The key name stays `pink` for BFF payload backwards
    // compatibility.
    expect(getBadgeColor("blue")).toEqual({
      bg: "var(--badge-blue-bg)",
      text: "var(--badge-blue-text)",
    });
    expect(getBadgeColor("pink")).toEqual({
      bg: "var(--badge-pink-bg)",
      text: "var(--badge-pink-text)",
    });
    expect(getBadgeColor("indigo")).toEqual({
      bg: "var(--badge-indigo-bg)",
      text: "var(--badge-indigo-text)",
    });
    expect(getBadgeColor("green")).toEqual({
      bg: "var(--badge-green-bg)",
      text: "var(--badge-green-text)",
    });
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

  it("defines every badge CSS variable in the imported shared token file", () => {
    for (const key of ["blue", "pink", "indigo", "green", "amber", "slate", undefined]) {
      const colors = getBadgeColor(key);
      for (const tokenRef of [colors.bg, colors.text]) {
        const match = tokenRef.match(/^var\((--[^)]+)\)$/);
        expect(match?.[1]).toBeTruthy();
        expect(sharedTokenCss).toContain(`${match?.[1]}:`);
      }
    }
  });
});
