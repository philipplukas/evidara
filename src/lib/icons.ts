// Icon Registry
// Maps iconKey strings from the BFF to emoji/text representations.
// In production, these would be SVG components or an icon library like circle-flags.

const iconMap: Record<string, string> = {
  ch: "🇨🇭",
  at: "🇦🇹",
  "ch-zh": "ZH",
  "ch-be": "BE",
  "ch-lu": "LU",
  "ch-sg": "SG",
  "ch-ag": "AG",
  "ch-ge": "GE",
  "ch-vd": "VD",
  "ch-ti": "TI",
};

export function getIcon(iconKey?: string): string | null {
  if (!iconKey) return null;
  return iconMap[iconKey] ?? null;
}
