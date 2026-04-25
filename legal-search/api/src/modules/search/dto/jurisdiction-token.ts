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

/**
 * Canonical platform-id parsing.
 *
 * Beyond the ISO tokens above, the search API also accepts the canonical
 * platform IDs frozen in `contracts/api/legal-search.openapi.yaml` (#423):
 *   - `jurisdiction_id` / `jurisdiction_ids`: `^jur_[a-z0-9_]+$`
 *     (e.g. `jur_ch_federal`, `jur_ch_zh`, `jur_ch_gemeinde_4001`,
 *     `jur_de_gemeinde_05111000`).
 *   - `authority_id` / `authority_ids`: `^auth_[a-z0-9_]+$`
 *     (e.g. `auth_fedlex`, `auth_de_bgh`).
 *
 * These route to the canonical `jurisdiction_ids` / `authority_ids`
 * arrays on the search projection (search-projection schema #423),
 * unlike ISO tokens which route to the legacy `jurisdiction` /
 * subdivision keyword fields. ISO and canonical filters are ANDed
 * server-side when both are present.
 *
 * Like the ISO parser: invalid tokens return `null`; list-form parsers
 * silently drop invalid entries.
 */

const JURISDICTION_ID_RE = /^jur_[a-z0-9_]+$/;
const AUTHORITY_ID_RE = /^auth_[a-z0-9_]+$/;

export function parseJurisdictionId(raw: string): string | null {
  if (typeof raw !== 'string') return null;
  const normalized = raw.trim().toLowerCase();
  if (!normalized || !JURISDICTION_ID_RE.test(normalized)) return null;
  return normalized;
}

export function parseAuthorityId(raw: string): string | null {
  if (typeof raw !== 'string') return null;
  const normalized = raw.trim().toLowerCase();
  if (!normalized || !AUTHORITY_ID_RE.test(normalized)) return null;
  return normalized;
}

export function parseJurisdictionIdList(raw: string | string[] | undefined): string[] {
  if (raw === undefined) return [];
  const tokens = Array.isArray(raw) ? raw : raw.split(',');
  return tokens
    .map((token) => parseJurisdictionId(token.trim()))
    .filter((value): value is string => value !== null);
}

export function parseAuthorityIdList(raw: string | string[] | undefined): string[] {
  if (raw === undefined) return [];
  const tokens = Array.isArray(raw) ? raw : raw.split(',');
  return tokens
    .map((token) => parseAuthorityId(token.trim()))
    .filter((value): value is string => value !== null);
}
