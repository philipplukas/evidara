/**
 * Jurisdiction token parsing.
 *
 * The legal-search `jurisdiction` query parameter accepts three shapes per
 * `contracts/api/legal-search.openapi.yaml` (v0.4.0):
 *   - ISO 3166-1 alpha-2 country code:   "CH", "DE", "EU"
 *   - ISO 3166-2 subdivision code:        "CH-ZH", "DE-BY", "IT-25"
 *   - Canonical platform-control ID:      "jur_ch_federal", "jur_ch_zh",
 *                                         "jur_ch_gemeinde_261", "jur_de_05315000"
 *
 * `parseJurisdictionToken` classifies an input string into one of those
 * three shapes (or returns `null` for malformed input). Callers route the
 * parsed token to the right OpenSearch field:
 *   - `iso-country`/`iso-subdivision`  -> `jurisdiction` keyword (existing
 *                                         country/subdivision behavior)
 *   - `canonical`                       -> `jurisdiction_ids.keyword` (the
 *                                         multi-valued projection field
 *                                         added by the canonical-ID
 *                                         routing slice; see #425)
 *
 * Invalid tokens return `null` — callers decide how to handle (400 vs drop).
 */

export type JurisdictionTokenKind = 'iso-country' | 'iso-subdivision' | 'canonical';

export interface ParsedJurisdictionToken {
  /** Which shape the input was. */
  kind: JurisdictionTokenKind;
  /**
   * ISO 3166-1 alpha-2 country, uppercased. Present for both ISO shapes.
   * Absent for canonical IDs — the canonical ID itself encodes the
   * country, but we don't decode it here (that's the projection's job).
   */
  country?: string;
  /**
   * ISO 3166-2 subdivision code (e.g. `CH-ZH`), uppercased. Only present
   * when `kind === 'iso-subdivision'`.
   */
  subdivision?: string;
  /**
   * Canonical platform-control jurisdiction id (`jur_<lower-snake>`).
   * Only present when `kind === 'canonical'`. Lowercased — the canonical
   * registry is lowercase-by-convention.
   */
  canonicalId?: string;
}

const ISO_RE = /^[A-Z]{2}(?:-[A-Z0-9]{1,3})?$/;
const CANONICAL_RE = /^jur_[a-z0-9_]+$/;

/**
 * Classify a single jurisdiction token. Returns `null` if the token
 * matches neither the ISO nor the canonical shape.
 *
 * Normalization rules:
 *   - ISO tokens are uppercased; surrounding whitespace is trimmed.
 *   - Canonical `jur_*` tokens are lowercased; surrounding whitespace is
 *     trimmed. The canonical registry is case-sensitive lowercase.
 */
export function parseJurisdictionToken(raw: string): ParsedJurisdictionToken | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;

  // Canonical IDs are case-sensitive lowercase by convention. We accept
  // mixed-case input defensively (lowercased before matching).
  const lowered = trimmed.toLowerCase();
  if (CANONICAL_RE.test(lowered)) {
    return { kind: 'canonical', canonicalId: lowered };
  }

  const upper = trimmed.toUpperCase();
  if (!ISO_RE.test(upper)) return null;
  const [country, subdivisionSuffix] = upper.split('-', 2);
  if (subdivisionSuffix === undefined) {
    return { kind: 'iso-country', country };
  }
  return { kind: 'iso-subdivision', country, subdivision: upper };
}

/**
 * Parse a list (CSV string or string[]) of jurisdiction tokens. Invalid
 * tokens are silently dropped — matches existing list-filter semantics
 * elsewhere in the BFF (see `normalizeCsv` in search-query.dto).
 */
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
 * Partition a parsed-token list by destination. Adapter code uses this to
 * build a single `bool.filter` array with both ISO-shape and canonical-shape
 * filters OR'd together (terms-on-different-fields semantics).
 */
export function partitionJurisdictionTokens(tokens: ParsedJurisdictionToken[]): {
  isoTokens: string[];
  canonicalIds: string[];
} {
  const isoTokens: string[] = [];
  const canonicalIds: string[] = [];
  for (const token of tokens) {
    if (token.kind === 'canonical' && token.canonicalId) {
      canonicalIds.push(token.canonicalId);
    } else if (token.kind === 'iso-subdivision' && token.subdivision) {
      // Existing behavior: subdivision filters route through the same
      // `jurisdiction` keyword field as country (the lowercased ISO token
      // is what the projection indexes today). Caller decides exact case.
      isoTokens.push(token.subdivision.toLowerCase());
    } else if (token.country) {
      isoTokens.push(token.country.toLowerCase());
    }
  }
  return { isoTokens, canonicalIds };
}
