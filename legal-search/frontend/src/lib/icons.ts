// Icon Registry
// Maps iconKey strings from the BFF to emoji/text representations.
//
// Sub-federal subdivision entries (ch-zh, at-w, de-by, fr-idf, it-25, …) are
// generated from contracts/vocabularies/subdivisions.json — do not edit
// SUBDIVISION_ICONS by hand. Regenerate with `npm run generate:icons`.
// Country entries and document-meta icons below are hand-maintained.

import { SUBDIVISION_ICONS } from "./subdivisions.generated";

const iconMap: Record<string, string> = {
  // ─── Countries ──────────────────────────────────────────────
  ch: "🇨🇭",
  at: "🇦🇹",
  de: "🇩🇪",
  fr: "🇫🇷",
  it: "🇮🇹",
  li: "🇱🇮",
  eu: "🇪🇺",

  // ─── Sub-federal subdivisions (generated from subdivisions.json) ──
  ...SUBDIVISION_ICONS,

  // ─── Document meta icons ────────────────────────────────────
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
