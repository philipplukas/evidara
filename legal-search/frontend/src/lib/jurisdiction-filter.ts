/**
 * Jurisdiction filter helper.
 *
 * The legal-search `jurisdiction` query parameter (see
 * contracts/api/legal-search.openapi.yaml) accepts either ISO 3166-1
 * country codes ("CH") or ISO 3166-2 subdivision codes ("CH-ZH"). This
 * module is the shared frontend helper for:
 *   1. Parsing a user-selected token into {country, subdivision?}.
 *   2. Listing the subdivisions available for a country (for pickers).
 *   3. Looking up the display label + iconKey for a token.
 *
 * All data comes from contracts/vocabularies/subdivisions.json via the
 * build-time generated map. No per-country hard-coding.
 */

import type { LanguageCode } from "./language";
import { SUBDIVISION_REGISTRY, SUBDIVISIONS_BY_COUNTRY } from "./subdivisions.generated";

export interface JurisdictionToken {
  /** ISO 3166-1 alpha-2 country, uppercase. */
  country: string;
  /** ISO 3166-2 subdivision, uppercase, when the token is sub-federal. */
  subdivision?: string;
}

export interface SubdivisionOption {
  iso: string;
  slug: string;
  iconKey: string;
  iconText: string;
  label: string;
  hierarchyPath: string;
}

const TOKEN_RE = /^[A-Z]{2}(?:-[A-Z0-9]{1,3})?$/;

export function parseJurisdictionToken(raw: string): JurisdictionToken | null {
  if (typeof raw !== "string") return null;
  const normalized = raw.trim().toUpperCase();
  if (!normalized || !TOKEN_RE.test(normalized)) return null;
  const [country, subdivisionSuffix] = normalized.split("-", 2);
  if (subdivisionSuffix === undefined) {
    return { country };
  }
  return { country, subdivision: normalized };
}

/**
 * Return the ordered list of subdivision options for a country, suitable
 * for rendering in a filter picker. Sorted by the ISO code for stable UI.
 * Returns an empty array for countries without subdivisions (e.g. EU, LI).
 */
export function subdivisionsForCountry(
  country: string,
  preferredLanguage: LanguageCode = "en",
): SubdivisionOption[] {
  const entries = SUBDIVISIONS_BY_COUNTRY[country.toUpperCase()] ?? [];
  return entries.map((iso) => {
    const entry = SUBDIVISION_REGISTRY[iso];
    const label =
      entry.prefLabel[preferredLanguage] ?? entry.prefLabel.en ?? entry.prefLabel.de ?? iso;
    return {
      iso,
      slug: entry.slug,
      iconKey: entry.iconKey,
      iconText: entry.iconText,
      label,
      hierarchyPath: entry.hierarchyPath,
    };
  });
}

/**
 * Return the display label for a jurisdiction token, falling back to the
 * token itself when no subdivision entry exists (e.g. for plain country
 * codes — use the country vocabulary separately for those).
 */
export function labelForSubdivisionToken(
  token: JurisdictionToken,
  preferredLanguage: LanguageCode = "en",
): string | null {
  if (!token.subdivision) return null;
  const entry = SUBDIVISION_REGISTRY[token.subdivision];
  if (!entry) return null;
  return (
    entry.prefLabel[preferredLanguage] ??
    entry.prefLabel.en ??
    entry.prefLabel.de ??
    token.subdivision
  );
}
