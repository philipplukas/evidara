/**
 * Generic badge color palette.
 *
 * The BFF assigns a colorKey from this palette to each badge.
 * The UI has no knowledge of what document types map to which colors —
 * that mapping lives in the BFF.
 *
 * Palette keys are visual aliases, not semantic:
 *   "blue", "pink", "indigo", "green" — not "law", "decision", etc.
 *
 * Note: the `pink` key was retuned to a neutral sky-blue (UX-7) because
 * the former pink/fuchsia hue combined with the red Swiss-cross flag icon
 * on result cards read as an error/destructive state. The key name is kept
 * for backwards compatibility with existing BFF payloads and mock data —
 * the BFF still owns the semantic mapping from document type to colorKey.
 */

const palette: Record<string, { bg: string; text: string }> = {
  blue: { bg: "#dbeafe", text: "#1e40af" },
  pink: { bg: "#e0f2fe", text: "#075985" },
  indigo: { bg: "#e0e7ff", text: "#3730a3" },
  green: { bg: "#d1fae5", text: "#065f46" },
  amber: { bg: "#fef3c7", text: "#92400e" },
  slate: { bg: "#f1f5f9", text: "#334155" },
};

const fallback = { bg: "#f3f4f6", text: "#374151" };

export function getBadgeColor(colorKey?: string): { bg: string; text: string } {
  return palette[colorKey || ""] || fallback;
}
