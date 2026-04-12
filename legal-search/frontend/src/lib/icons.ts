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
  "dtype-law": "§",
  "dtype-decision": "⚖",
  "dtype-commentary": "💬",
  "dtype-rechtssatz": "≡",
  "meta-status": "●",
  "meta-calendar": "📅",
  "meta-citation": "↗",
  "meta-official": "✓",
  "meta-language": "🌐",
  "meta-authority": "🏛",
};

export function getIcon(iconKey?: string): string | null {
  if (!iconKey) return null;
  return iconMap[iconKey] ?? null;
}
