/**
 * Generic badge color palette.
 *
 * The BFF assigns a colorKey from this palette to each badge.
 * The UI has no knowledge of what document types map to which colors —
 * that mapping lives in the BFF.
 *
 * Palette keys are visual, not semantic:
 *   "blue", "pink", "indigo", "green" — not "law", "decision", etc.
 */

const palette: Record<string, { bg: string; text: string }> = {
  blue:   { bg: "#dbeafe", text: "#1e40af" },
  pink:   { bg: "#fce7f3", text: "#9d174d" },
  indigo: { bg: "#e0e7ff", text: "#3730a3" },
  green:  { bg: "#d1fae5", text: "#065f46" },
  amber:  { bg: "#fef3c7", text: "#92400e" },
  slate:  { bg: "#f1f5f9", text: "#334155" },
};

const fallback = { bg: "#f3f4f6", text: "#374151" };

export function getBadgeColor(colorKey?: string): { bg: string; text: string } {
  return palette[colorKey || ""] || fallback;
}
