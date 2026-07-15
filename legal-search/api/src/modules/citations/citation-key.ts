/**
 * Canonical citation keys — the TypeScript mirror of document-intelligence's
 * `normalize_citation()` (`nlp/citation_extractor.py`).
 *
 * DI produces these keys at extraction time and writes them onto each citation
 * row as `normalized_reference`. This module produces the SAME key from a raw
 * citation string typed by a human or an agent ("SR 210", "Art. 36 BV"), so
 * that `resolve_citation(text)` can join against the `citation-targets` index
 * without a round-trip through DI.
 *
 * Key format: `{type}:{value}` — identical on both sides. If the two ever
 * drift, the graph silently loses edges, so the shapes are deliberately kept
 * dumb and literal, and `citation-key.spec.ts` pins the exact keys DI emits.
 *
 * DELIBERATE SCOPE (#582): only the DETERMINISTIC citation types are ported —
 * the ones where the string itself contains the identifier. Fuzzy types (bare
 * "Art. 36 BV", BGE references, German statute paragraphs) need search-based
 * resolution against the corpus; DI returns `None` for them too, and they are
 * reported honestly as unresolved rather than guessed at. See the follow-up
 * issue referenced in the PR.
 */

/** Swiss SR (Systematische Rechtssammlung) number: "SR 210", "SR 311.0". */
const SR_PATTERN = /\bSR\s+(\d{3}(?:\.\d+)*)\b/i;

/** EU CELEX number: "32016R0679". */
const CELEX_PATTERN = /\b([1-9]\d{4}[A-Z]{1,2}\d{4})\b/;

/** ECLI (any jurisdiction): "ECLI:CH:BGER:2023:1C.123.2022". */
const ECLI_PATTERN = /\bECLI:[A-Z]{2}:[A-Z0-9]+:\d{4}:[A-Z0-9.]+\b/i;

/** EU regulation in prose form: "Regulation (EU) 2016/679". */
const EU_REGULATION_PATTERN =
  /\b(?:regulation|verordnung|règlement)\b[^\d]{0,20}(\d{4})\/(\d{1,4})/i;

/** EU directive in prose form: "Directive 95/46/EC". */
const EU_DIRECTIVE_PATTERN = /\b(?:directive|richtlinie)\b[^\d]{0,20}(\d{4})\/(\d{1,4})/i;

/** Austrian Bundesgesetzblatt: "BGBl. I Nr. 43/1975". */
const AT_BGBL_PATTERN = /\bBGBl\.\s*(?:[IVX]+\s+)?Nr\.\s*(\d+)\/(\d{4})\b/i;

/**
 * Turn a raw citation string into the canonical `{type}:{value}` key, or
 * `null` when the string is a fuzzy reference that needs search-based
 * resolution (mirroring `normalize_citation`'s `None`).
 *
 * Matching is ordered most-specific-first: an ECLI contains digits that could
 * otherwise be mistaken for a CELEX number.
 */
export function normalizeCitationText(text: string): string | null {
  const input = text.trim();
  if (!input) return null;

  // Already a canonical key (`sr:210`) — accept it verbatim so callers can
  // pass either form. Guarded to the key types we actually mint.
  const asKey = parseCitationKey(input);
  if (asKey) return `${asKey.identifierType}:${asKey.identifierValue}`;

  const ecli = input.match(ECLI_PATTERN);
  if (ecli) return `ecli:${ecli[0].toUpperCase()}`;

  const sr = input.match(SR_PATTERN);
  if (sr) return `sr:${sr[1]}`;

  const bgbl = input.match(AT_BGBL_PATTERN);
  if (bgbl) return `at_bgbl:${bgbl[1]}/${bgbl[2]}`;

  // Prose EU references resolve to a CELEX key, exactly as DI does:
  // sector 3, year, R|L, zero-padded ordinal.
  const regulation = input.match(EU_REGULATION_PATTERN);
  if (regulation) return `celex:3${regulation[1]}R${regulation[2].padStart(4, '0')}`;

  const directive = input.match(EU_DIRECTIVE_PATTERN);
  if (directive) return `celex:3${directive[1]}L${directive[2].padStart(4, '0')}`;

  const celex = input.match(CELEX_PATTERN);
  if (celex) return `celex:${celex[1]}`;

  // Fuzzy — needs search-based resolution. Reported, never guessed.
  return null;
}

/** The identifier types this API mints and resolves deterministically. */
const KNOWN_IDENTIFIER_TYPES = new Set([
  'sr',
  'celex',
  'ecli',
  'at_bgbl',
  'de_docket',
  'de_statute',
  'fr_pourvoi',
  'fr_ce',
  'it_cass',
  'it_cds',
  'it_codice',
  'official_citation',
]);

/**
 * Split a canonical key into its parts, or `null` if the string is not a
 * key of a type we know. Used by the resolver to build the term filters and
 * by callers passing `sr:210` straight through.
 */
export function parseCitationKey(
  key: string,
): { identifierType: string; identifierValue: string } | null {
  const colonIdx = key.indexOf(':');
  if (colonIdx <= 0) return null;

  const identifierType = key.slice(0, colonIdx).toLowerCase();
  const identifierValue = key.slice(colonIdx + 1);
  if (!identifierValue) return null;

  // ECLIs are the one ambiguous case, because an ECLI is itself colon-delimited
  // and DI keys them as `ecli:<full ECLI>` — i.e. `ecli:ECLI:CH:BGER:...`.
  // Splitting on the first colon must therefore distinguish:
  //   `ecli:ECLI:CH:...`  (canonical key)  -> value is the remainder
  //   `ECLI:CH:BGER:...`  (a raw ECLI)     -> value is the WHOLE string
  if (identifierType === 'ecli') {
    const isCanonicalKey = /^ecli:/i.test(identifierValue);
    return {
      identifierType: 'ecli',
      identifierValue: (isCanonicalKey ? identifierValue : key).toUpperCase(),
    };
  }

  if (!KNOWN_IDENTIFIER_TYPES.has(identifierType)) return null;

  return { identifierType, identifierValue };
}
