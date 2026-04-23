/**
 * --text-meta contrast — Unit Tests
 *
 * WHY THIS TEST EXISTS:
 * Secondary metadata text (result-card meta row, scope bar, context-bar
 * filter/reset link, detail-sheet field labels) is rendered against the
 * cream `--surface-page` canvas. `--muted-foreground` alone measures
 * ~3.94:1 against #e4e9ef — below the WCAG AA 4.5:1 floor for normal
 * text (flagged in design review of #384, tracked in #386).
 *
 * The fix introduces a new semantic token `--text-meta` whose values
 * are tuned to clear WCAG AA on both page and panel surfaces, in both
 * light and dark themes. This test pins those contrast ratios so any
 * future token tweak that regresses AA fails loudly.
 *
 * Source of truth for token values: `styles/tokens/tokens.ts` (light
 * exports) + `styles/tokens/tokens.css` `.dark` block (dark values
 * inlined here until a typed dark-theme mirror exists — see #279 / M5).
 */

import { SURFACE_PAGE, SURFACE_PANEL, TEXT_META, TEXT_META_DARK } from "@evidara/tokens";
import { describe, expect, it } from "vitest";

// Dark surface hexes — mirror of .dark block in tokens.css.
// Kept here because tokens.ts does not (yet) expose a dark-theme mirror.
const SURFACE_PAGE_DARK = "#0f1419";
const SURFACE_PANEL_DARK = "#1a2028";

const WCAG_AA_NORMAL = 4.5;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const linearize = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

function contrast(fg: string, bg: string): number {
  const fgL = relativeLuminance(hexToRgb(fg));
  const bgL = relativeLuminance(hexToRgb(bg));
  const [hi, lo] = fgL > bgL ? [fgL, bgL] : [bgL, fgL];
  return (hi + 0.05) / (lo + 0.05);
}

describe("--text-meta contrast (WCAG AA)", () => {
  it("light: TEXT_META on SURFACE_PAGE clears 4.5:1", () => {
    expect(contrast(TEXT_META, SURFACE_PAGE)).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });

  it("light: TEXT_META on SURFACE_PANEL clears 4.5:1", () => {
    expect(contrast(TEXT_META, SURFACE_PANEL)).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });

  it("dark: TEXT_META_DARK on dark page surface clears 4.5:1", () => {
    expect(contrast(TEXT_META_DARK, SURFACE_PAGE_DARK)).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });

  it("dark: TEXT_META_DARK on dark panel surface clears 4.5:1", () => {
    expect(contrast(TEXT_META_DARK, SURFACE_PANEL_DARK)).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });
});
