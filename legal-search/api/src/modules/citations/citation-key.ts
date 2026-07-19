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
 * SCOPE (#582, extended by #594): the deterministic citation types, plus
 * article references ("Art. 36 BV") via `abbrev_art:`.
 *
 * #594 asked for SEARCH-BASED resolution of article references. Measuring
 * first showed that was the wrong tool. "Art. 36 BV" needs no ranking: the
 * short title is an identifier, and Fedlex already publishes it as
 * `title_short`. So resolution here is a deterministic lookup against
 * `citation-targets`, and the corpus — not a similarity score — decides
 * whether the norm exists. A ranking-based resolver would have produced a
 * confident edge for every one of the 187 phantom "citations" the extractor
 * was manufacturing from the BV's own article headings.
 *
 * Still NOT resolved here, and reported unresolved rather than guessed: BGE
 * references, German statute paragraphs (`de_statute:BGB` names a statute but
 * not a provision), and cross-lingual short titles (`Cst.`/`Cost.` are the
 * BV's French and Italian names; nothing yet links them to `BV`).
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
 * Article reference against a statute short title: "Art. 36 BV",
 * "Art. 36 Abs. 2 BV", "Art. 261bis StGB".
 *
 * Mirrors `_ARTICLE_PATTERN` in `nlp/citation_extractor.py`. Abs./lit. are
 * matched so they do not break the parse, but are NOT part of the key: they
 * subdivide within an article, and the article is the addressable unit (#573).
 */
const ARTICLE_PATTERN =
  /\bArt\.?\s+(\d+(?:bis|ter|quater|quinquies|sexies)?)(?:\s+(?:Abs|al|cpv)\.?\s+\d+)?(?:\s+(?:lit|let)\.?\s+[a-z])?\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöü]*)\b/;

/**
 * A statute short title carries AT LEAST TWO capitals: BV, OR, ZGB, StGB,
 * SchKG, EMRK, LugÜ. Mirrors `_LEGAL_ABBREVIATION_SHAPE` in DI.
 *
 * This is a SHAPE test, never a dictionary — we do not assert what an
 * abbreviation means, only that it is shaped like one. It is what stops
 * "Art. 36 Einschränkungen von Grundrechten" (the BV's own heading) from
 * being read as a citation to a statute called "Einschränkungen".
 */
const LEGAL_ABBREVIATION_SHAPE = /^(?=(?:.*[A-ZÄÖÜ]){2})[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*$/;

/** True when `token` is SHAPED like a statute short title (>= 2 capitals). */
export function isLegalAbbreviation(token: string): boolean {
  return LEGAL_ABBREVIATION_SHAPE.test(token);
}

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

  // "Art. 36 BV" — the short title plus the article number IS an identifier,
  // PROVIDED the corpus knows what the short title abbreviates. This function
  // only mints the key; whether a node with that key exists is answered by
  // `citation-targets`, and a miss is reported as `no_target_in_corpus`
  // (a coverage gap) rather than guessed at.
  const article = input.match(ARTICLE_PATTERN);
  if (article && isLegalAbbreviation(article[2])) {
    return `abbrev_art:${article[2]}/${article[1]}`;
  }

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
  /** A statute by its short title: `abbrev:BV` -> the Bundesverfassung. */
  'abbrev',
  /** A PROVISION: `abbrev_art:BV/36` -> the BV's Art. 36 section. */
  'abbrev_art',
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
