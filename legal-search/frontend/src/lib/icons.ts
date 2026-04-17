// Icon Registry
//
// Two rendering modes the consumer picks between at the callsite:
//   1. `isFlagIcon(key)` → `<img src={getFlagSrc(key)}/>` for countries with a
//      shipped SVG flag (see public/flags/).
//   2. Everything else falls through to `getIcon(key)` which returns a text or
//      emoji representation from `textIconMap`.
//
// Sub-federal subdivision entries (ch-zh, at-w, de-by, fr-idf, it-25, …) are
// generated from contracts/vocabularies/subdivisions.json — do not edit
// SUBDIVISION_ICONS by hand. Regenerate with `npm run generate:icons`.
// Country-level emoji fallbacks (for countries without an SVG flag asset) and
// document-meta icons below are hand-maintained.

import { SUBDIVISION_ICONS } from "./subdivisions.generated";

const FLAG_KEYS: Record<string, string> = {
  ch: "/flags/ch.svg",
  at: "/flags/at.svg",
};

const FLAG_ALT: Record<string, string> = {
  ch: "Switzerland",
  at: "Austria",
};

const textIconMap: Record<string, string> = {
  // ─── Country emoji fallbacks (for countries without an SVG flag asset) ──
  // CH and AT go through `isFlagIcon`/`getFlagSrc` SVG path; the others
  // render emoji via `getIcon`. Add an SVG under public/flags/<iso>.svg
  // and extend FLAG_KEYS above to upgrade a country from emoji → SVG.
  de: "🇩🇪",
  fr: "🇫🇷",
  it: "🇮🇹",
  li: "🇱🇮",
  eu: "🇪🇺",

  // ─── Sub-federal subdivisions (generated from subdivisions.json) ──
  ...SUBDIVISION_ICONS,

  // ─── Document meta icons ──────────────────────────────────────────
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

export function isFlagIcon(iconKey?: string): boolean {
  return !!iconKey && iconKey in FLAG_KEYS;
}

export function getFlagSrc(iconKey: string): string | null {
  return FLAG_KEYS[iconKey] ?? null;
}

export function getFlagAlt(iconKey: string): string {
  return FLAG_ALT[iconKey] ?? iconKey.toUpperCase();
}

export function getIcon(iconKey?: string): string | null {
  if (!iconKey) return null;
  return textIconMap[iconKey] ?? null;
}
