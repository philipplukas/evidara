// Icon Registry
//
// Three rendering modes, resolved in this order. Consumers should not branch by
// hand — render `<MetadataIcon iconKey={…}/>` (components/primitives), which is
// the single place that walks them:
//   1. `getIconComponent(key)` → a monochrome lucide component. This is the
//      default treatment for every document-meta key, and is themeable (it
//      inherits `currentColor` and takes a design token via className).
//   2. `isFlagIcon(key)` → `<img src={getFlagSrc(key)}/>` for countries with a
//      shipped SVG flag (see public/flags/).
//   3. `getIcon(key)` → a text glyph from `textIconMap`, for jurisdiction
//      identity only (country emoji fallbacks + generated subdivisions).
//
// Jurisdiction identity is the deliberate exception to "monochrome lucide
// everywhere": a flag/canton mark is the thing it depicts and has no stroke-icon
// equivalent. Every *semantic* icon (document type, status, language, authority,
// …) must live in `META_ICON_COMPONENTS` below and never in `textIconMap` — a
// colour emoji beside a lucide stroke icon is what #694 was filed for.
//
// Sub-federal subdivision entries (ch-zh, at-w, de-by, fr-idf, it-25, …) are
// generated from contracts/vocabularies/subdivisions.json — do not edit
// SUBDIVISION_ICONS by hand. Regenerate with `npm run generate:icons`.
// Country-level emoji fallbacks (for countries without an SVG flag asset) are
// hand-maintained; upgrade one by shipping public/flags/<iso>.svg and adding it
// to FLAG_KEYS.

import {
  AlignLeft,
  ArrowUpRight,
  BadgeCheck,
  Calendar,
  Circle,
  Globe,
  Landmark,
  type LucideIcon,
  MessageSquare,
  Scale,
  Scroll,
} from "lucide-react";

import { SUBDIVISION_ICONS } from "./subdivisions.generated";

const FLAG_KEYS: Record<string, string> = {
  ch: "/flags/ch.svg",
  at: "/flags/at.svg",
};

const FLAG_ALT: Record<string, string> = {
  ch: "Switzerland",
  at: "Austria",
};

// ─── Document meta icons (monochrome lucide, themeable) ───────────────
//
// Keys are emitted by the BFF — see
// legal-search/api/src/core/presentation/metadata-icons.ts. Adding a key there
// without adding it here renders nothing, which the icon-system test catches.
const META_ICON_COMPONENTS: Record<string, LucideIcon> = {
  "dtype-law": Scroll, // was §
  "dtype-decision": Scale, // was ⚖
  "dtype-commentary": MessageSquare, // was 💬
  "dtype-rechtssatz": AlignLeft, // was ≡
  "meta-status": Circle, // was ●
  "meta-calendar": Calendar, // was 📅
  "meta-citation": ArrowUpRight, // was ↗
  "meta-official": BadgeCheck, // was ✓
  "meta-language": Globe, // was 🌐 — the lucide Globe already used for the
  // translation chip in ResultCard, so the same
  // semantic now renders the same mark (#694)
  "meta-authority": Landmark, // was 🏛
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

  // NOTE: the dtype-*/meta-* keys deliberately do NOT live here — they resolve
  // to lucide components via META_ICON_COMPONENTS (#694).
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

/**
 * The lucide component for a document-meta key, or null when the key is a
 * jurisdiction mark (flag / subdivision glyph) that has no stroke-icon form.
 */
export function getIconComponent(iconKey?: string): LucideIcon | null {
  if (!iconKey) return null;
  return META_ICON_COMPONENTS[iconKey] ?? null;
}

export function getIcon(iconKey?: string): string | null {
  if (!iconKey) return null;
  return textIconMap[iconKey] ?? null;
}

/** Every key this registry can render, in any of the three modes. */
export function knownIconKeys(): string[] {
  return [
    ...new Set([
      ...Object.keys(META_ICON_COMPONENTS),
      ...Object.keys(FLAG_KEYS),
      ...Object.keys(textIconMap),
    ]),
  ];
}
