/**
 * Generic badge color palette.
 *
 * The BFF assigns a colorKey from this palette to each badge.
 * The UI has no knowledge of what document types map to which colors —
 * that mapping lives in the BFF.
 *
 * Palette keys are visual, not semantic:
 *   "blue", "pink", "indigo", "green" — not "law", "decision", etc.
 *
 * Values resolve to CSS custom properties defined in
 * `contracts/design-tokens/evidara-tokens.css` so swatches stay in
 * sync across apps and pick up dark-mode overrides automatically.
 */

type BadgeColor = { bg: string; text: string };

const palette: Record<string, BadgeColor> = {
  blue: { bg: "var(--badge-blue-bg)", text: "var(--badge-blue-text)" },
  pink: { bg: "var(--badge-pink-bg)", text: "var(--badge-pink-text)" },
  indigo: { bg: "var(--badge-indigo-bg)", text: "var(--badge-indigo-text)" },
  green: { bg: "var(--badge-green-bg)", text: "var(--badge-green-text)" },
  amber: { bg: "var(--badge-amber-bg)", text: "var(--badge-amber-text)" },
  slate: { bg: "var(--badge-slate-bg)", text: "var(--badge-slate-text)" },
};

const fallback: BadgeColor = {
  bg: "var(--badge-fallback-bg)",
  text: "var(--badge-fallback-text)",
};

export function getBadgeColor(colorKey?: string): BadgeColor {
  return palette[colorKey || ""] || fallback;
}
