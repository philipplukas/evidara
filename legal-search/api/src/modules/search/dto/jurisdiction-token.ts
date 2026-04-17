/**
 * Jurisdiction token parsing.
 *
 * The legal-search `jurisdiction` query parameter accepts two shapes per
 * `contracts/api/legal-search.openapi.yaml`:
 *   - ISO 3166-1 alpha-2 country code: "CH", "DE", "EU"
 *   - ISO 3166-2 subdivision code:      "CH-ZH", "DE-BY", "IT-25"
 *
 * `parseJurisdictionToken` normalizes either form and reports whether the
 * token carries a sub-federal scope. Called by the BFF (see SearchQueryDto)
 * and will be called by any future projection code that needs to route
 * filters to the right OpenSearch field.
 *
 * Invalid tokens return `null` — callers decide how to handle (400 vs drop).
 */

export interface ParsedJurisdictionToken {
  /** ISO 3166-1 alpha-2 country, uppercased. Always present. */
  country: string;
  /** ISO 3166-2 subdivision code, uppercased. Absent when only the country was cited. */
  subdivision?: string;
}

const TOKEN_RE = /^[A-Z]{2}(?:-[A-Z0-9]{1,3})?$/;

export function parseJurisdictionToken(raw: string): ParsedJurisdictionToken | null {
  if (typeof raw !== 'string') return null;
  const normalized = raw.trim().toUpperCase();
  if (!normalized || !TOKEN_RE.test(normalized)) return null;
  const [country, subdivisionSuffix] = normalized.split('-', 2);
  if (subdivisionSuffix === undefined) {
    return { country };
  }
  return { country, subdivision: normalized };
}

export function parseJurisdictionList(
  raw: string | string[] | undefined,
): ParsedJurisdictionToken[] {
  if (raw === undefined) return [];
  const tokens = Array.isArray(raw) ? raw : raw.split(',');
  return tokens
    .map((token) => parseJurisdictionToken(token.trim()))
    .filter((parsed): parsed is ParsedJurisdictionToken => parsed !== null);
}
